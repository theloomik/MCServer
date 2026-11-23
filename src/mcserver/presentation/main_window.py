"""Main window: sidebar with servers, dashboard for the selected server, menu and status bar."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QWidget,
)

from mcserver.application.backups import BackupInfo
from mcserver.application.errors import InvalidJavaExecutable, JavaNotFound, JavaVersionTooOld
from mcserver.application.java_setup import JavaStatus
from mcserver.application.ports import StartOptions
from mcserver.application.server_health import UncleanShutdown
from mcserver.application.server_management import LegacyImportResult
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.presentation import theme
from mcserver.presentation.adapters.output_bridge import OutputBridge
from mcserver.presentation.adapters.status_poller import StatusPoller
from mcserver.presentation.controllers.backups import BackupsController
from mcserver.presentation.controllers.console import ConsoleController
from mcserver.presentation.controllers.properties import PropertiesController
from mcserver.presentation.controllers.server_creation import ServerCreationController
from mcserver.presentation.controllers.server_dashboard import ServerDashboardController
from mcserver.presentation.controllers.server_list import ServerListController, ServerListState
from mcserver.presentation.controllers.server_management import ManagementController
from mcserver.presentation.dialogs.adopt_server_dialog import AdoptServerDialog
from mcserver.presentation.dialogs.create_server_dialog import CreateServerDialog
from mcserver.presentation.dialogs.delete_server_dialog import DeleteServerDialog
from mcserver.presentation.dialogs.edit_server_dialog import EditServerDialog
from mcserver.presentation.dialogs.error_details_dialog import ErrorDetailsDialog
from mcserver.presentation.dialogs.java_setup_dialog import JavaChoice, JavaSetupDialog, pick_java_with_system_dialog
from mcserver.presentation.dialogs.settings_dialog import SettingsDialog
from mcserver.presentation.errors import UserMessage, describe_error, render_message
from mcserver.presentation.i18n import Messages
from mcserver.presentation.services import PresentationServices
from mcserver.presentation.views.backups_view import BackupsView, format_created_at
from mcserver.presentation.views.server_dashboard_view import ServerDashboardView
from mcserver.presentation.views.server_list_view import ServerListView
from mcserver.presentation.views.server_properties_view import ServerPropertiesView
from mcserver.presentation.workers import BackgroundRunner

_logger = logging.getLogger(__name__)
_NO_TOOLTIP = ""
METRICS_INTERVAL_MS = 2000
BACKUP_CHECK_INTERVAL_MS = 60_000

ConfirmExit = Callable[[str], bool]
FolderOpener = Callable[[Path], bool]
CreateDialogFactory = Callable[[ServerCreationController, Messages, QWidget], CreateServerDialog]
Confirm = Callable[[str], bool]
"""Ask a yes/no question about ``server_id``; return the answer."""
JavaProblem = JavaNotFound | JavaVersionTooOld
JavaProblemHandler = Callable[[JavaProblem], JavaChoice]
UncleanNotifier = Callable[[UncleanShutdown], None]
AskDelete = Callable[[ServerConfiguration, Path], bool | None]
"""Return ``None`` to cancel, else whether the folder goes to the Recycle Bin too."""
LegacyOffer = Callable[[int], bool]
LegacyResultNotifier = Callable[[LegacyImportResult], None]
ConfirmBackup = Callable[[BackupInfo], bool]
"""Ask whether to restore or delete a backup; return the answer."""
LogPathChooser = Callable[[str], str]
"""Ask where to save ``server_id``'s console log; ``""`` cancels."""


class StopTimeoutChoice(Enum):
    """What to do when the graceful stop before exiting timed out."""

    KEEP_WAITING = "keep_waiting"
    KILL = "kill"
    CANCEL = "cancel"


AskAfterStopTimeout = Callable[[str, float], StopTimeoutChoice]


def open_folder_with_system(path: Path) -> bool:
    """Open ``path`` in the system file manager; return whether it worked."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class MainWindow(QMainWindow):
    """Top-level window: builds controllers and views from services and wires them together.

    The window never builds or closes backend services (``app.py`` owns them).
    Closing it while a server runs asks for confirmation, stops the server
    gracefully in the background and closes once it has stopped. If that stop
    times out, the user chooses to keep waiting, kill the server or cancel the
    close; nothing is killed without that choice (ADR 0006).
    """

    def __init__(
        self,
        services: PresentationServices,
        messages: Messages,
        parent: QWidget | None = None,
        *,
        confirm_exit: ConfirmExit | None = None,
        open_folder: FolderOpener = open_folder_with_system,
        create_dialog: CreateDialogFactory = CreateServerDialog,
        confirm_kill: Confirm | None = None,
        confirm_eula: Confirm | None = None,
        handle_java_problem: JavaProblemHandler | None = None,
        notify_unclean: UncleanNotifier | None = None,
        ask_after_stop_timeout: AskAfterStopTimeout | None = None,
        ask_delete: AskDelete | None = None,
        offer_legacy_import: LegacyOffer | None = None,
        notify_legacy_result: LegacyResultNotifier | None = None,
        confirm_restore: ConfirmBackup | None = None,
        confirm_delete_backup: ConfirmBackup | None = None,
        choose_log_path: LogPathChooser | None = None,
        auto_restart_delay_ms: int | None = None,
    ) -> None:
        """Build the window from already-created services and messages, then load the servers."""
        super().__init__(parent)
        self._services = services
        self._messages = messages
        self._confirm_exit = confirm_exit or self._ask_to_stop_and_exit
        self._open_folder = open_folder
        self._create_dialog_factory = create_dialog
        self._confirm_kill = confirm_kill or self._ask_to_kill
        self._confirm_eula = confirm_eula or self._ask_to_accept_eula
        self._handle_java_problem = handle_java_problem or self._show_java_dialog
        self._notify_unclean = notify_unclean or self._show_unclean_notice
        self._ask_after_stop_timeout = ask_after_stop_timeout or self._ask_after_timeout
        self._ask_delete = ask_delete or self._show_delete_dialog
        self._offer_legacy_import = offer_legacy_import or self._ask_legacy_import
        self._notify_legacy_result = notify_legacy_result or self._show_legacy_result
        self._confirm_restore = confirm_restore or self._ask_to_restore
        self._confirm_delete_backup = confirm_delete_backup or self._ask_to_delete_backup
        self._choose_log_path = choose_log_path or self._ask_log_path
        self.create_dialog: CreateServerDialog | None = None
        self.edit_dialog: EditServerDialog | None = None
        self.adopt_dialog: AdoptServerDialog | None = None
        self.settings_dialog: SettingsDialog | None = None
        self._exit_after_stop = False
        self._torn_down = False
        self.setWindowTitle(messages.text("app.title"))
        self.resize(1280, 800)
        self.setMinimumSize(980, 620)
        self.setStyleSheet(theme.STYLESHEET)

        self.background = BackgroundRunner(parent=self)
        coordinator = services.coordinator
        self.poller = StatusPoller(coordinator, parent=self) if coordinator is not None else None
        self.output_bridge = OutputBridge(services.output, self) if services.output is not None else None
        self.server_list_controller = ServerListController(services.management, coordinator, self)
        restart_delay = {} if auto_restart_delay_ms is None else {"auto_restart_delay_ms": auto_restart_delay_ms}
        self.dashboard_controller = ServerDashboardController(
            coordinator, self.poller, self.background, self, auto_restart=services.auto_restart, **restart_delay
        )
        self.console_controller = ConsoleController(self.output_bridge, parent=self)
        # Creation needs no Java: it is available without Java as well.
        self.creation_controller = ServerCreationController(
            services.server_creation, services.management, self.background, self
        )
        self.management_controller = ManagementController(services, self.background, self)
        self.properties_controller = PropertiesController(services.properties, self)
        self.backups_controller = BackupsController(
            services.backups, self.background, self, schedules=services.scheduled_backups
        )
        self.backup_timer = QTimer(self)
        self.backup_timer.setInterval(BACKUP_CHECK_INTERVAL_MS)
        self.backup_timer.timeout.connect(self.backups_controller.run_scheduled)

        self.server_list_view = ServerListView(messages)
        self.dashboard_view = ServerDashboardView(messages, services.servers_root, self.console_controller.available)
        self.properties_view: ServerPropertiesView | None = None
        if self.properties_controller.available:
            self.properties_view = ServerPropertiesView(messages)
            self.dashboard_view.add_tab("properties", self.properties_view)
        self.backups_view: BackupsView | None = None
        if self.backups_controller.available:
            self.backups_view = BackupsView(messages)
            self.dashboard_view.add_tab("backups", self.backups_view)
        self.dashboard_view.set_metrics_available(services.metrics is not None)
        self.metrics_timer = QTimer(self)
        self.metrics_timer.setInterval(METRICS_INTERVAL_MS)
        self.metrics_timer.timeout.connect(self.sample_metrics)

        self._build_menu()
        self._build_content()
        self._build_status_bar()
        self._connect()

        if self.poller is not None:
            self.poller.start()
        if services.metrics is not None:
            self.metrics_timer.start()
        if services.scheduled_backups is not None and services.backups is not None:
            self.backup_timer.start()
        self.server_list_controller.refresh()
        # Shown once the window is up: incidents from the previous session (M1-GUI-06),
        # then the one-time offer to import MCServer 0.9.1 servers (M2-GUI-02).
        QTimer.singleShot(0, self._after_start)

    # --- construction ---------------------------------------------------------------------

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(self._messages.text("menu.file"))
        self.new_server_action = file_menu.addAction(self._messages.text("menu.file.new_server"))
        self.new_server_action.setShortcut(QKeySequence(QKeySequence.StandardKey.New))
        self.refresh_action = file_menu.addAction(self._messages.text("menu.file.refresh"))
        self.refresh_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Refresh))
        self.import_folder_action = file_menu.addAction(self._messages.text("menu.file.import_folder"))
        self.import_legacy_action = file_menu.addAction(self._messages.text("menu.file.import_legacy"))
        file_menu.addSeparator()
        self.settings_action = file_menu.addAction(self._messages.text("menu.file.settings"))
        file_menu.addSeparator()
        self.exit_action = file_menu.addAction(self._messages.text("menu.file.exit"))
        self.exit_action.triggered.connect(self.close)

    def _build_content(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.server_list_view.setFixedWidth(280)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.server_list_view)
        layout.addWidget(self.dashboard_view, 1)
        self.setCentralWidget(central)

    def _build_status_bar(self) -> None:
        status_bar = self.statusBar()
        self.servers_folder_label = QLabel(
            self._messages.text("status.servers_folder", path=str(self._services.servers_root))
        )
        self.servers_folder_label.setObjectName("serversFolder")
        if self._services.can_run_servers and not self._services.java_problem:
            java_text = self._messages.text("status.java_available")
        else:
            java_text = self._messages.text("status.java_missing")
        self.java_status_label = QLabel(java_text)
        self.java_status_label.setObjectName("javaStatus")
        if self._services.java_problem:
            # Technical detail stays out of the main text; available on hover.
            self.java_status_label.setToolTip(self._services.java_problem)
        status_bar.addWidget(self.servers_folder_label, 1)
        status_bar.addPermanentWidget(self.java_status_label)
        self.java_check_button = QPushButton(self._messages.text("status.java_check"))
        self.java_check_button.setObjectName("javaCheck")
        self.java_choose_button = QPushButton(self._messages.text("status.java_choose"))
        self.java_choose_button.setObjectName("javaChoose")
        if self._services.java is not None:
            status_bar.addPermanentWidget(self.java_check_button)
            status_bar.addPermanentWidget(self.java_choose_button)
        else:
            self.java_check_button.hide()
            self.java_choose_button.hide()

    def _connect(self) -> None:
        servers = self.server_list_controller
        servers.state_changed.connect(self._show_list_state)
        self.server_list_view.server_selected.connect(servers.select)
        self.server_list_view.refresh_requested.connect(servers.refresh)
        self.refresh_action.triggered.connect(servers.refresh)
        self.server_list_view.create_requested.connect(self.open_create_dialog)
        self.new_server_action.triggered.connect(self.open_create_dialog)
        self.creation_controller.created.connect(self._on_server_created)
        if self.poller is not None:
            self.poller.changed.connect(lambda _snapshot: servers.update_statuses())

        dashboard = self.dashboard_controller
        dashboard.state_changed.connect(self.dashboard_view.show_state)
        dashboard.state_changed.connect(
            lambda _state: self.backups_controller.set_active_server(self.dashboard_controller.active_server_id)
        )
        dashboard.operation_finished.connect(self._on_operation_finished)
        dashboard.eula_required.connect(self._on_eula_required)
        dashboard.java_problem.connect(self._on_java_problem)
        dashboard.stop_timed_out.connect(self._on_stop_timed_out)
        self.dashboard_view.start_requested.connect(lambda: dashboard.start())
        self.dashboard_view.stop_requested.connect(dashboard.stop)
        self.dashboard_view.restart_requested.connect(dashboard.restart)
        self.dashboard_view.kill_requested.connect(self.request_kill)
        self.dashboard_view.details_requested.connect(self.show_details)
        self.dashboard_view.open_folder_requested.connect(self._open_server_folder)
        self.dashboard_view.open_logs_requested.connect(self._open_logs_folder)
        self.dashboard_view.copy_address_requested.connect(self._copy_address)
        self.java_check_button.clicked.connect(self.check_java)
        self.java_choose_button.clicked.connect(self.choose_java)

        management = self.management_controller
        self.dashboard_view.edit_requested.connect(self.open_edit_dialog)
        self.dashboard_view.delete_requested.connect(self.request_delete)
        self.import_folder_action.triggered.connect(self.open_adopt_dialog)
        self.import_legacy_action.triggered.connect(management.import_legacy)
        self.settings_action.triggered.connect(self.open_settings_dialog)
        management.changed.connect(self._on_servers_changed)
        management.message.connect(self._show_message_in_status_bar)
        management.failed.connect(self._show_message_in_status_bar)
        management.legacy_imported.connect(self._notify_legacy_result)

        properties = self.properties_controller
        if self.properties_view is not None:
            properties.state_changed.connect(self.properties_view.show_state)
            properties.state_changed.connect(lambda state: self.show_address(state.server_id))
            self.properties_view.save_requested.connect(properties.save)
            self.properties_view.reload_requested.connect(lambda: properties.reload())
        backups = self.backups_controller
        if self.backups_view is not None:
            backups.state_changed.connect(self.backups_view.show_state)
            backups.progress.connect(self.backups_view.show_progress)
            self.backups_view.create_requested.connect(backups.create)
            self.backups_view.restore_requested.connect(self.request_restore)
            self.backups_view.delete_requested.connect(self.request_delete_backup)
            self.backups_view.schedule_changed.connect(backups.save_schedule)
        backups.scheduled_finished.connect(self._show_message_in_status_bar)

        console = self.console_controller
        console.lines_appended.connect(self.dashboard_view.console.append_lines)
        console.cleared.connect(self.dashboard_view.console.clear)
        self.dashboard_view.console.clear_requested.connect(console.clear)
        self.dashboard_view.console.save_requested.connect(self.save_console_log)
        self.dashboard_view.console.command_submitted.connect(dashboard.send_command)

    # --- behaviour --------------------------------------------------------------------------

    def _show_list_state(self, state: ServerListState) -> None:
        self.server_list_view.show_state(state)
        self.dashboard_controller.show_server(state.selected)
        self.dashboard_view.show_details_error(state.details_error_key)
        selected_id = state.selected.server_id if state.selected else None
        self.console_controller.show_server(selected_id)
        self.properties_controller.show_server(selected_id)
        self.backups_controller.show_server(selected_id)
        self.backups_controller.set_active_server(self.dashboard_controller.active_server_id)
        self.sample_metrics()
        self.show_address(selected_id)

    def open_create_dialog(self) -> None:
        """Show the create-server dialog (only one at a time)."""
        if self.create_dialog is not None:
            self.create_dialog.raise_()
            self.create_dialog.activateWindow()
            return
        dialog = self._create_dialog_factory(self.creation_controller, self._messages, self)
        dialog.finished.connect(self._on_create_dialog_finished)
        self.create_dialog = dialog
        dialog.open()

    def _on_create_dialog_finished(self, _result: int) -> None:
        dialog, self.create_dialog = self.create_dialog, None
        if dialog is not None:
            dialog.deleteLater()

    def _on_server_created(self, configuration: ServerConfiguration) -> None:
        """Show the new server: reload the list, select it and confirm on its dashboard."""
        server_id = configuration.server_id
        self.server_list_controller.refresh()
        self.server_list_controller.select(server_id)
        self.dashboard_controller.report_created(server_id)
        self.statusBar().showMessage(self._messages.text("create.done", server_id=server_id), 6000)

    def _open_server_folder(self, path: Path) -> None:
        if not self._open_folder(path):
            self.statusBar().showMessage(self._messages.text("dashboard.open_folder_failed", path=str(path)), 6000)

    def _on_operation_finished(self) -> None:
        if self._exit_after_stop and self.dashboard_controller.active_server_id is None:
            self._exit_after_stop = False
            self.close()

    # --- M3: resources, backups ---------------------------------------------------------------

    def sample_metrics(self) -> None:
        """Show CPU, memory and uptime when the selected server is the running one."""
        metrics = self._services.metrics
        if metrics is None:
            return
        try:
            snapshot = metrics.sample()
        except Exception:
            _logger.debug("Could not read process metrics.", exc_info=True)
            snapshot = None
        row = self.dashboard_controller.state.row
        if snapshot is not None and (row is None or snapshot.server_id != row.server_id):
            snapshot = None
        self.dashboard_view.show_metrics(snapshot)
        activity = self._services.activity
        if activity is None or snapshot is None:
            self.dashboard_view.show_activity(None)
        else:
            self.dashboard_view.show_activity(activity.snapshot(snapshot.server_id))

    def show_address(self, server_id: str | None) -> None:
        """Show the LAN address of ``server_id`` in the server card (M3-GUI-05)."""
        lookup = self._services.address
        address = lookup.address(server_id) if lookup is not None and server_id is not None else None
        self.dashboard_view.show_address(address)

    def _copy_address(self, text: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            self.statusBar().showMessage(self._messages.text("dashboard.address_copied", address=text), 4000)

    def _open_logs_folder(self, path: Path) -> None:
        if not path.is_dir():
            self.statusBar().showMessage(self._messages.text("dashboard.no_logs"), 6000)
            return
        self._open_server_folder(path)

    def save_console_log(self) -> None:
        """Save the console lines of the selected server to a file the user picks (M3-GUI-01)."""
        server_id = self.console_controller.server_id
        if server_id is None:
            return
        path = self._choose_log_path(server_id)
        if not path:
            return
        try:
            Path(path).write_text(self.dashboard_view.console.log_text(), encoding="utf-8")
        except OSError as error:
            _logger.warning("Could not save the console log to %s: %s", path, error)
            self.statusBar().showMessage(self._messages.text("console.save_failed", path=path), 8000)
            return
        self.statusBar().showMessage(self._messages.text("console.saved", path=path), 6000)

    def request_restore(self, backup: BackupInfo) -> None:
        """Restore ``backup`` after a double confirmation."""
        if self._confirm_restore(backup):
            self.backups_controller.restore(backup)

    def request_delete_backup(self, backup: BackupInfo) -> None:
        """Move ``backup`` to the Recycle Bin after confirmation."""
        if self._confirm_delete_backup(backup):
            self.backups_controller.delete(backup)

    def open_backups(self, server_id: str) -> None:
        """Select ``server_id`` and show its backups."""
        self.server_list_controller.select(server_id)
        self.dashboard_view.show_tab("backups")

    def _server_name(self, server_id: str) -> str:
        configuration = self._selected_configuration()
        if configuration is not None and configuration.server_id == server_id:
            return configuration.name
        return server_id

    # --- kill, details, EULA, Java, incidents ---------------------------------------------

    def request_kill(self) -> None:
        """Kill the active server after an explicit confirmation that warns about data loss."""
        active = self.dashboard_controller.active_server_id
        if active is not None and self._confirm_kill(active):
            self.dashboard_controller.kill()

    def show_details(self, message: UserMessage) -> None:
        """Show the technical details of a banner message."""
        dialog = ErrorDetailsDialog(message, self._messages, self)
        dialog.finished.connect(dialog.deleteLater)
        dialog.open()

    def _on_eula_required(self, server_id: str) -> None:
        provisioning = self._services.provisioning
        if provisioning is None or not self._confirm_eula(server_id):
            return
        self.background.run(
            lambda: provisioning.accept_eula(server_id),
            lambda _result: self.dashboard_controller.start(),
            self._show_error_in_status_bar,
        )

    def _on_java_problem(self, problem: JavaProblem) -> None:
        if self._services.java is None:
            return
        choice = self._handle_java_problem(problem)
        self.check_java()
        if choice is JavaChoice.RETRY:
            self.dashboard_controller.start()
        elif choice is JavaChoice.START_ANYWAY:
            self.dashboard_controller.start(StartOptions(allow_outdated_java=True))

    def check_java(self) -> None:
        """Detect Java again and update the status bar (no restart needed)."""
        java = self._services.java
        if java is not None:
            self._show_java_status(java.status())

    def choose_java(self) -> None:
        """Let the user choose ``java.exe`` for later starts."""
        java = self._services.java
        if java is None:
            return
        path = pick_java_with_system_dialog(self._messages)(self)
        if not path:
            return
        try:
            self._show_java_status(java.choose_executable(path))
        except InvalidJavaExecutable as error:
            self._show_error_in_status_bar(error)

    def _show_java_status(self, status: JavaStatus) -> None:
        installation = status.installation
        if installation is None:
            self.java_status_label.setText(self._messages.text("status.java_missing"))
            self.java_status_label.setToolTip(_NO_TOOLTIP)
            return
        self.java_status_label.setText(self._messages.text("status.java_ready", major=installation.major_version))
        self.java_status_label.setToolTip(installation.executable)

    def _show_error_in_status_bar(self, error: BaseException) -> None:
        self.statusBar().showMessage(render_message(self._messages, describe_error(error)), 8000)

    def _show_message_in_status_bar(self, message: UserMessage) -> None:
        self.statusBar().showMessage(render_message(self._messages, message), 8000)

    # --- M2: edit, delete, import, settings ---------------------------------------------------

    def _selected_configuration(self) -> ServerConfiguration | None:
        row = self.dashboard_controller.state.row
        return row.configuration if row is not None else None

    def _on_servers_changed(self, server_id: object) -> None:
        self.server_list_controller.refresh()
        if isinstance(server_id, str):
            self.server_list_controller.select(server_id)

    def open_edit_dialog(self) -> None:
        """Edit the selected server (folder and JAR are locked while it runs)."""
        configuration = self._selected_configuration()
        if configuration is None:
            return
        running = self.dashboard_controller.active_server_id == configuration.server_id
        dialog = EditServerDialog(self.management_controller, configuration, self._messages, self, running=running)
        self.edit_dialog = dialog
        dialog.finished.connect(lambda _result: self._forget_dialog("edit_dialog"))
        dialog.open()

    def request_delete(self) -> None:
        """Delete the selected, stopped server after confirmation."""
        configuration = self._selected_configuration()
        if configuration is None or self.dashboard_controller.active_server_id == configuration.server_id:
            return
        remove_files = self._ask_delete(configuration, self.management_controller.server_folder(configuration))
        if remove_files is not None:
            self.management_controller.delete(configuration, remove_files=remove_files)

    def open_adopt_dialog(self) -> None:
        """Import an existing server folder."""
        if self.adopt_dialog is not None:
            self.adopt_dialog.raise_()
            return
        dialog = AdoptServerDialog(self.management_controller, self._messages, self)
        self.adopt_dialog = dialog
        dialog.finished.connect(lambda _result: self._forget_dialog("adopt_dialog"))
        dialog.open()

    def open_settings_dialog(self) -> None:
        """Show the application settings."""
        settings = self._services.settings
        if settings is None:
            return
        dialog = SettingsDialog(
            self.management_controller,
            settings.current,
            self._services.java,
            self._messages,
            self,
            open_folder=self._open_folder,
        )
        dialog.import_legacy_requested.connect(self.management_controller.import_legacy)
        dialog.accepted.connect(self.check_java)
        self.settings_dialog = dialog
        dialog.finished.connect(lambda _result: self._forget_dialog("settings_dialog"))
        dialog.open()

    def _forget_dialog(self, name: str) -> None:
        dialog = getattr(self, name)
        setattr(self, name, None)
        if dialog is not None:
            dialog.deleteLater()

    def _after_start(self) -> None:
        self.report_unclean_shutdowns()
        self.offer_legacy_import()

    def offer_legacy_import(self) -> None:
        """Offer once to import MCServer 0.9.1 servers that are not in the list yet."""
        controller = self.management_controller
        if not controller.should_offer_legacy_import():
            return
        pending = controller.pending_legacy_servers()
        controller.mark_legacy_import_offered()
        if self._offer_legacy_import(len(pending)):
            controller.import_legacy()

    def report_unclean_shutdowns(self) -> None:
        """Tell the user once about each server that was not stopped cleanly last time (no recovery offered yet)."""
        health = self._services.health
        if health is None:
            return
        for incident in health.unclean_shutdowns():
            self._notify_unclean(incident)
            try:
                health.acknowledge(incident.server_id)
            except Exception:
                # A marker that cannot be removed is reported again on the next launch.
                _logger.exception("Could not acknowledge the incident for %r.", incident.server_id)

    def _on_stop_timed_out(self, server_id: str) -> None:
        if not self._exit_after_stop:
            return
        choice = self._ask_after_stop_timeout(server_id, self.dashboard_controller.stop_timeout)
        if choice is StopTimeoutChoice.KEEP_WAITING:
            self.dashboard_controller.stop_active(server_id)
        elif choice is StopTimeoutChoice.KILL:
            self.dashboard_controller.kill()
        else:
            self._exit_after_stop = False

    # --- default dialogs --------------------------------------------------------------------

    def _ask_to_stop_and_exit(self, server_id: str) -> bool:
        answer = QMessageBox.question(
            self,
            self._messages.text("exit.confirm.title"),
            self._messages.text("exit.confirm.text", server_id=server_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _show_delete_dialog(self, configuration: ServerConfiguration, folder: Path) -> bool | None:
        dialog = DeleteServerDialog(configuration, folder, self._messages, self)
        accepted = dialog.exec() == DeleteServerDialog.DialogCode.Accepted
        remove_files = dialog.remove_files
        dialog.deleteLater()
        return remove_files if accepted else None

    def _ask_legacy_import(self, count: int) -> bool:
        answer = QMessageBox.question(
            self,
            self._messages.text("legacy.offer.title"),
            self._messages.plural("legacy.offer.text", count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _show_legacy_result(self, result: LegacyImportResult) -> None:
        if not (result.imported or result.skipped or result.rejected):
            text = self._messages.text("legacy.result.nothing")
        else:
            lines = [
                self._messages.text(
                    "legacy.result.text",
                    imported=result.imported_count,
                    skipped=result.skipped_count,
                    rejected=result.rejected_count,
                )
            ]
            lines += [
                self._messages.text("legacy.result.rejected", server_id=item.server_id, reason=item.reason)
                for item in result.rejected
            ]
            text = "\n".join(lines)
        QMessageBox.information(self, self._messages.text("legacy.result.title"), text)

    def _ask_to_kill(self, server_id: str) -> bool:
        answer = QMessageBox.warning(
            self,
            self._messages.text("kill.confirm.title"),
            self._messages.text("kill.confirm.text", server_id=server_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _ask_to_accept_eula(self, server_id: str) -> bool:
        answer = QMessageBox.question(
            self,
            self._messages.text("eula.title"),
            self._messages.text("eula.text", server_id=server_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _show_java_dialog(self, problem: JavaProblem) -> JavaChoice:
        java = self._services.java
        if java is None:
            return JavaChoice.CANCELLED
        dialog = JavaSetupDialog(problem, java, self._messages, self)
        dialog.exec()
        return dialog.choice

    def _show_unclean_notice(self, incident: UncleanShutdown) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self._messages.text("unclean.title", server_id=incident.server_id))
        box.setText(
            self._messages.text("unclean.text", server_id=incident.server_id, started_at=incident.started_at or "?")
        )
        box.addButton(QMessageBox.StandardButton.Ok)
        backups = None
        if self.backups_controller.available:
            backups = box.addButton(self._messages.text("unclean.open_backups"), QMessageBox.ButtonRole.ActionRole)
        box.exec()
        if backups is not None and box.clickedButton() is backups:
            self.open_backups(incident.server_id)

    def _ask_log_path(self, server_id: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path, _filter = QFileDialog.getSaveFileName(
            self,
            self._messages.text("console.save_title"),
            str(Path.home() / f"{server_id}-console-{stamp}.log"),
            self._messages.text("console.save_filter"),
        )
        return path

    def _ask_to_restore(self, backup: BackupInfo) -> bool:
        name = self._server_name(backup.server_id)
        yes, cancel = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Cancel
        first = QMessageBox.warning(
            self,
            self._messages.text("backups.restore.title", backup_id=backup.backup_id),
            self._messages.text("backups.restore.text", name=name),
            yes | cancel,
            cancel,
        )
        if first != yes:
            return False
        second = QMessageBox.warning(
            self,
            self._messages.text("backups.restore.confirm_title"),
            self._messages.text(
                "backups.restore.confirm_text", name=name, created_at=format_created_at(backup.created_at)
            ),
            yes | cancel,
            cancel,
        )
        return second == yes

    def _ask_to_delete_backup(self, backup: BackupInfo) -> bool:
        answer = QMessageBox.question(
            self,
            self._messages.text("backups.delete.title", backup_id=backup.backup_id),
            self._messages.text("backups.delete.text"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _ask_after_timeout(self, server_id: str, timeout: float) -> StopTimeoutChoice:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self._messages.text("exit.stop_timed_out.title"))
        box.setText(self._messages.text("exit.stop_timed_out.text", server_id=server_id, timeout=f"{timeout:g}"))
        wait = box.addButton(self._messages.text("exit.keep_waiting"), QMessageBox.ButtonRole.AcceptRole)
        kill = box.addButton(self._messages.text("exit.kill"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(self._messages.text("exit.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(wait)
        box.exec()
        clicked = box.clickedButton()
        if clicked is wait:
            return StopTimeoutChoice.KEEP_WAITING
        if clicked is kill:
            return StopTimeoutChoice.KILL
        return StopTimeoutChoice.CANCEL

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop a running server (after confirmation) before closing; release GUI resources."""
        if (
            self.dashboard_controller.busy
            or self.creation_controller.busy
            or self.management_controller.busy
            or self.backups_controller.busy
        ):
            event.ignore()
            self.statusBar().showMessage(self._messages.text("exit.wait_for_operation"), 6000)
            return
        active = self.dashboard_controller.active_server_id
        if active is not None:
            event.ignore()
            if self._confirm_exit(active) and self.dashboard_controller.stop_active(active):
                self._exit_after_stop = True
                self.statusBar().showMessage(self._messages.text("exit.stopping", server_id=active))
            return
        self._tear_down()
        super().closeEvent(event)

    def _tear_down(self) -> None:
        if self._torn_down:
            return
        self._torn_down = True
        if self.poller is not None:
            self.poller.stop()
        self.metrics_timer.stop()
        self.backup_timer.stop()
        self.console_controller.close()
        self.background.dispose()
