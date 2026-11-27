"""Main window: sidebar with servers, dashboard for the selected server, menu and status bar."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from pathlib import Path

import shiboken6
from PySide6.QtCore import QLocale, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QDesktopServices,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from mcserver.application.backups import BackupInfo
from mcserver.application.errors import InvalidJavaExecutable, JavaNotFound, JavaVersionTooOld
from mcserver.application.java_setup import JavaStatus
from mcserver.application.ports import StartOptions
from mcserver.application.server_health import UncleanShutdown
from mcserver.application.server_management import LegacyImportResult
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.presentation import appearance, icons, theme
from mcserver.presentation.adapters.output_bridge import OutputBridge
from mcserver.presentation.adapters.status_poller import StatusPoller
from mcserver.presentation.controllers.backups import BackupsController
from mcserver.presentation.controllers.console import ConsoleController
from mcserver.presentation.controllers.first_run import Ending, FirstRunController
from mcserver.presentation.controllers.jar_catalog import JarCatalogController
from mcserver.presentation.controllers.properties import PropertiesController
from mcserver.presentation.controllers.server_creation import ServerCreationController
from mcserver.presentation.controllers.server_dashboard import ServerDashboardController
from mcserver.presentation.controllers.server_list import ServerListController, ServerListState
from mcserver.presentation.controllers.server_management import ManagementController
from mcserver.presentation.controllers.worlds import WorldsController
from mcserver.presentation.dialogs.adopt_server_dialog import AdoptServerDialog
from mcserver.presentation.dialogs.confirm_dialog import Choice, ask
from mcserver.presentation.dialogs.create_server_dialog import CreateServerDialog
from mcserver.presentation.dialogs.delete_server_dialog import DeleteServerDialog
from mcserver.presentation.dialogs.download_jar_dialog import DownloadJarDialog
from mcserver.presentation.dialogs.edit_server_dialog import EditServerDialog
from mcserver.presentation.dialogs.error_details_dialog import ErrorDetailsDialog
from mcserver.presentation.dialogs.first_run import FirstRunDialog
from mcserver.presentation.dialogs.java_setup_dialog import JavaChoice, JavaSetupDialog, pick_java_with_system_dialog
from mcserver.presentation.dialogs.settings_dialog import SettingsDialog
from mcserver.presentation.dialogs.world_dialogs import QtWorldDialogs, WorldDialogs
from mcserver.presentation.errors import UserMessage, describe_error, render_message
from mcserver.presentation.i18n import Messages, resolve_language
from mcserver.presentation.notifications import NotificationCenter
from mcserver.presentation.services import PresentationServices
from mcserver.presentation.views.backups_view import BackupsView, format_created_at
from mcserver.presentation.views.page_host import PageHost
from mcserver.presentation.views.server_dashboard_view import ServerDashboardView
from mcserver.presentation.views.server_list_view import ServerListView
from mcserver.presentation.views.server_properties_view import ServerPropertiesView
from mcserver.presentation.views.toasts import ToastStack
from mcserver.presentation.views.worlds_view import WorldsView
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


def _dot(color: str, size: int = 8) -> QPixmap:
    image = QPixmap(size * 2, size * 2)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(0, 0, 0, 0))
    painter.setBrush(QColor(color))
    painter.drawEllipse(2, 2, size * 2 - 4, size * 2 - 4)
    painter.end()
    image.setDevicePixelRatio(2.0)
    return image


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

    language_change_requested = Signal(str)
    """Language or theme changed; ``app.py`` replaces this window with one built in ``language`` and the current theme."""

    def __init__(
        self,
        services: PresentationServices,
        messages: Messages,
        parent: QWidget | None = None,
        *,
        confirm_exit: ConfirmExit | None = None,
        open_folder: FolderOpener = open_folder_with_system,
        create_dialog: CreateDialogFactory | None = None,
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
        world_dialogs: WorldDialogs | None = None,
        first_run_guide: bool = False,
    ) -> None:
        """Build the window from already-created services and messages, then load the servers.

        With ``first_run_guide`` (the application passes it) the setup guide opens at startup
        until it was finished or skipped once, as long as there are no servers yet.
        """
        super().__init__(parent)
        self._services = services
        self._messages = messages
        self._confirm_exit = confirm_exit or self._ask_to_stop_and_exit
        self._open_folder = open_folder
        self._create_dialog_factory = create_dialog or self._default_create_dialog
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
        self._world_dialogs = world_dialogs or QtWorldDialogs(self, messages)
        self.create_dialog: CreateServerDialog | None = None
        self._first_run_guide = first_run_guide
        self.first_run_controller: FirstRunController | None = None
        self.first_run_dialog: FirstRunDialog | None = None
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
        self.worlds_controller = WorldsController(services.worlds, self.background, self)
        self.jar_catalog_controller = (
            JarCatalogController(services.jar_catalog, self.background, self) if services.jar_catalog else None
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
        self.worlds_view: WorldsView | None = None
        if self.worlds_controller.available:
            self.worlds_view = WorldsView(messages)
            self.dashboard_view.add_tab("worlds", self.worlds_view)
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
        self.first_run_action = file_menu.addAction(self._messages.text("menu.file.first_run"))
        file_menu.addSeparator()
        self.settings_action = file_menu.addAction(self._messages.text("menu.file.settings"))
        self.settings_action.setShortcut(QKeySequence("Ctrl+,"))
        file_menu.addSeparator()
        self.exit_action = file_menu.addAction(self._messages.text("menu.file.exit"))
        self.exit_action.triggered.connect(self.close)

        self._build_view_menu()

        # Server menu: the selected server's actions, enabled exactly like their buttons (M4 design).
        server_menu = self.menuBar().addMenu(self._messages.text("menu.server"))
        view = self.dashboard_view
        self.server_actions: dict[str, tuple[QAction, QPushButton]] = {}
        groups = (
            (
                ("start", view.start_button, "Ctrl+R"),
                ("stop", view.stop_button, None),
                ("restart", view.restart_button, None),
                ("kill", view.kill_button, None),
            ),
            (("open_folder", view.open_folder_button, None), ("open_logs", view.open_logs_button, None)),
            (("edit", view.edit_button, None), ("delete", view.delete_button, None)),
        )
        for index, group in enumerate(groups):
            if index:
                server_menu.addSeparator()
            for key, source, shortcut in group:
                action = server_menu.addAction(self._messages.text(f"menu.server.{key}"))
                if shortcut:
                    action.setShortcut(QKeySequence(shortcut))
                action.triggered.connect(source.click)
                self.server_actions[key] = (action, source)
        self._update_server_menu()

    def _build_view_menu(self) -> None:
        """Keyboard ways to every area (M4-GUI-07): tabs, the server list and the console command."""
        view_menu = self.menuBar().addMenu(self._messages.text("menu.view"))
        self.tab_actions: dict[str, QAction] = {}
        for number, key in enumerate(self.dashboard_view.tab_keys, start=1):
            action = view_menu.addAction(self._messages.text(f"tabs.{key}"))
            if number <= 9:
                action.setShortcut(QKeySequence(f"Ctrl+{number}"))
            action.triggered.connect(lambda _checked=False, tab=key: self.dashboard_view.show_tab(tab))
            self.tab_actions[key] = action
        view_menu.addSeparator()
        self.focus_list_action = view_menu.addAction(self._messages.text("menu.view.server_list"))
        self.focus_list_action.setShortcut(QKeySequence("Ctrl+L"))
        self.focus_list_action.triggered.connect(self.focus_server_list)
        self.focus_console_action = view_menu.addAction(self._messages.text("menu.view.console"))
        self.focus_console_action.setShortcut(QKeySequence("Ctrl+K"))
        self.focus_console_action.triggered.connect(self.focus_console)

    def focus_server_list(self) -> None:
        """Move the keyboard focus to the server list."""
        self.server_list_view.list_widget.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def focus_console(self) -> None:
        """Show the Overview tab and put the focus in the console command line."""
        if self.page_host.pages:
            return  # a page is open; its own fields keep the focus
        self.dashboard_view.show_tab("overview")
        console_input = self.dashboard_view.console.input
        if console_input.isEnabled():
            console_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        else:
            self.dashboard_view.console.text.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _build_content(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        # Dialogs open as pages in the content area; the server list stays visible (M4 design).
        self.page_host = PageHost(self.dashboard_view)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.server_list_view)
        layout.addWidget(self.page_host, 1)
        self.setCentralWidget(central)
        # Notifications float at the bottom right, over pages too (M4-GUI-04).
        self.notifications = NotificationCenter(self)
        self.toast_stack = ToastStack(self._messages, central)
        self.notifications.changed.connect(self.toast_stack.show_state)
        self.toast_stack.dismiss_requested.connect(self.notifications.dismiss)
        self.toast_stack.dismiss_all_requested.connect(self.notifications.dismiss_all)
        self.toast_stack.details_requested.connect(self.show_details)
        self.toast_stack.hover_changed.connect(self.notifications.hold)

    def show_page(self, dialog: QDialog, *, compact: bool = False) -> None:
        """Open ``dialog`` as a page in the content area (it closes itself when finished)."""
        self.page_host.open_page(dialog, compact=compact)

    def run_page(self, dialog: QDialog, *, compact: bool = True) -> int:
        """Open ``dialog`` as a page and wait for its answer; return its result code."""
        return self.page_host.run_page(dialog, compact=compact)

    def _on_dashboard_state(self, _state: object) -> None:
        # A bound method (not a lambda) is disconnected when this window is deleted.
        self._track_active_server()
        self._update_server_menu()

    def _update_server_menu(self) -> None:
        """Mirror the toolbar: a menu action is enabled when its button is usable."""
        has_server = self.dashboard_controller.state.row is not None
        for action, source in self.server_actions.values():
            if not (shiboken6.isValid(action) and shiboken6.isValid(source)):
                return  # the window is being deleted; a late result must not touch its menu
            action.setEnabled(has_server and source.isEnabled() and not source.isHidden())

    def _build_status_bar(self) -> None:
        status_bar = self.statusBar()
        folder_icon = QLabel()
        folder_icon.setPixmap(icons.pixmap("folder", theme.TEXT_MUTED, 14))
        status_bar.addWidget(folder_icon)
        self.servers_folder_label = QLabel(
            self._messages.text("status.servers_folder", path=str(self._services.servers_root))
        )
        self.servers_folder_label.setObjectName("serversFolder")
        # A long path is cut off rather than widening the window; the tooltip has all of it.
        self.servers_folder_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.servers_folder_label.setToolTip(str(self._services.servers_root))
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
        self.java_dot = QLabel()
        self.java_dot.setObjectName("javaDot")
        self._set_java_dot(self._services.can_run_servers and not self._services.java_problem)
        status_bar.addPermanentWidget(self.java_dot)
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
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme)
        servers = self.server_list_controller
        servers.state_changed.connect(self._show_list_state)
        self.server_list_view.server_selected.connect(self._on_server_picked)
        self.server_list_view.refresh_requested.connect(servers.refresh)
        self.refresh_action.triggered.connect(servers.refresh)
        self.server_list_view.create_requested.connect(self.open_create_dialog)
        self.server_list_view.import_requested.connect(self.open_adopt_dialog)
        self.server_list_view.settings_requested.connect(self.open_settings_dialog)
        self.dashboard_view.new_server_requested.connect(self.open_create_dialog)
        self.dashboard_view.import_requested.connect(self.open_adopt_dialog)
        self.new_server_action.triggered.connect(self.open_create_dialog)
        self.creation_controller.created.connect(self._on_server_created)
        if self.poller is not None:
            self.poller.changed.connect(lambda _snapshot: servers.update_statuses())

        dashboard = self.dashboard_controller
        dashboard.state_changed.connect(self.dashboard_view.show_state)
        dashboard.state_changed.connect(self._on_dashboard_state)
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
        self.first_run_action.triggered.connect(self.open_first_run)
        self.settings_action.triggered.connect(self.open_settings_dialog)
        management.changed.connect(self._on_servers_changed)
        management.message.connect(self._show_message_in_status_bar)
        management.failed.connect(self._show_failure)
        management.legacy_imported.connect(self._on_legacy_imported)

        properties = self.properties_controller
        if self.properties_view is not None:
            properties.state_changed.connect(self.properties_view.show_state)
            properties.state_changed.connect(lambda state: self.show_address(state.server_id))
            self.properties_view.save_requested.connect(properties.save)
            self.properties_view.reload_requested.connect(lambda: properties.reload())
        worlds = self.worlds_controller
        if self.worlds_view is not None:
            worlds.state_changed.connect(self.worlds_view.show_state)
            worlds.progress.connect(self.worlds_view.show_progress)
            self.worlds_view.cancel_requested.connect(worlds.cancel)
            self.worlds_view.use_requested.connect(worlds.use_world)
            self.worlds_view.new_requested.connect(self.request_new_world)
            self.worlds_view.import_folder_requested.connect(lambda: self.request_import_world(zip_file=False))
            self.worlds_view.import_zip_requested.connect(lambda: self.request_import_world(zip_file=True))
            self.worlds_view.export_requested.connect(self.request_export_world)
            self.worlds_view.delete_requested.connect(self.request_delete_world)
        # The current world lives in server.properties: keep both tabs in step.
        worlds.level_changed.connect(lambda: self.properties_controller.reload())
        properties.state_changed.connect(self._on_properties_state)
        backups = self.backups_controller
        if self.backups_view is not None:
            backups.state_changed.connect(self.backups_view.show_state)
            backups.progress.connect(self.backups_view.show_progress)
            self.backups_view.cancel_requested.connect(backups.cancel)
            self.backups_view.create_requested.connect(backups.create)
            self.backups_view.restore_requested.connect(self.request_restore)
            self.backups_view.delete_requested.connect(self.request_delete_backup)
            self.backups_view.schedule_changed.connect(backups.save_schedule)
        backups.scheduled_finished.connect(self.notify)

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
        self.dashboard_view.show_details_error(state.details_error_key, has_servers=bool(state.servers))
        selected_id = state.selected.server_id if state.selected else None
        self.console_controller.show_server(selected_id)
        self.properties_controller.show_server(selected_id)
        self.worlds_controller.show_server(selected_id)
        self.worlds_controller.set_active_server(self.dashboard_controller.active_server_id)
        self.backups_controller.show_server(selected_id)
        self.backups_controller.set_active_server(self.dashboard_controller.active_server_id)
        self.sample_metrics()
        self.show_address(selected_id)

    def _on_server_picked(self, server_id: object) -> None:
        """Picking a server closes open pages first; a page that is still working keeps the old selection."""
        if not self.page_host.dismiss_all():
            self.server_list_view.show_state(self.server_list_controller.state)
            return
        self.server_list_controller.select(server_id if isinstance(server_id, str) else None)

    def open_create_dialog(self) -> None:
        """Show the create-server dialog (only one at a time)."""
        if self.create_dialog is not None:
            return  # already open as a page
        dialog = self._create_dialog_factory(self.creation_controller, self._messages, self)
        dialog.finished.connect(self._on_create_dialog_finished)
        self.create_dialog = dialog
        self.show_page(dialog)

    def _default_create_dialog(
        self, controller: ServerCreationController, messages: Messages, parent: QWidget
    ) -> CreateServerDialog:
        download = self.download_server_jar if self.jar_catalog_controller is not None else None
        return CreateServerDialog(controller, messages, parent, download_jar=download)

    def download_server_jar(self, parent: QWidget) -> str | None:
        """Let the user pick and download an official server JAR; return the verified file (M3-GUI-06)."""
        controller = self.jar_catalog_controller
        if controller is None:
            return None
        dialog = DownloadJarDialog(controller, self._messages, parent)
        self.run_page(dialog, compact=False)
        path = dialog.path
        dialog.deleteLater()
        return path

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
        self.notify(UserMessage("create.done", {"server_id": server_id}), "success")

    def _open_server_folder(self, path: Path) -> None:
        if not self._open_folder(path):
            self.notify(UserMessage("dashboard.open_folder_failed", {"path": str(path)}), "error")

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
        history = self._services.metrics_history
        if snapshot is not None:
            history.add(snapshot)  # the running server's history, whichever server is selected
        row = self.dashboard_controller.state.row
        if snapshot is not None and (row is None or snapshot.server_id != row.server_id):
            snapshot = None
        self.dashboard_view.show_metrics(snapshot)
        self.dashboard_view.show_history(
            history.points(row.server_id if row is not None else None), live=snapshot is not None
        )
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
            self.notify(UserMessage("dashboard.address_copied", {"address": text}), "success")

    def _open_logs_folder(self, path: Path) -> None:
        if not path.is_dir():
            self.notify(UserMessage("dashboard.no_logs"), "notice")
            return
        self._open_server_folder(path)

    def _track_active_server(self) -> None:
        active = self.dashboard_controller.active_server_id
        self.backups_controller.set_active_server(active)
        self.worlds_controller.set_active_server(active)

    def _on_properties_state(self, state: object) -> None:
        message = getattr(state, "message", None)
        if message is not None and message.key in ("properties.saved", "properties.saved_restart"):
            self.worlds_controller.refresh()

    def request_new_world(self) -> None:
        """Ask for a name and seed; the server generates the world on its next start (M3-GUI-07)."""
        answer = self._world_dialogs.new_world()
        if answer is not None:
            self.worlds_controller.create_world(*answer)

    def request_import_world(self, *, zip_file: bool) -> None:
        """Copy a world from a folder or ZIP file into the selected server."""
        service, server_id = self.worlds_controller.service, self.worlds_controller.state.server_id
        if service is None or server_id is None:
            return
        source = self._world_dialogs.import_source(zip_file)
        if source is None:
            return
        try:
            suggested = service.suggest_name(server_id, Path(source).stem)
        except Exception as error:
            self._show_error_in_status_bar(error)
            return
        name = self._world_dialogs.world_name(suggested)
        if name is not None:
            self.worlds_controller.import_world(source, name)

    def request_export_world(self, name: str) -> None:
        """Write world ``name`` into a ZIP file the user picks."""
        target = self._world_dialogs.export_path(name)
        if target is not None:
            self.worlds_controller.export_world(name, target)

    def request_delete_world(self, name: str) -> None:
        """Move world ``name`` to the Recycle Bin after confirmation."""
        if self._world_dialogs.confirm_delete(name):
            self.worlds_controller.delete_world(name)

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
            self.notify(UserMessage("console.save_failed", {"path": path}), "error")
            return
        self.notify(UserMessage("console.saved", {"path": path}), "success")

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
        self.show_page(dialog)

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
        self._set_java_dot(installation is not None)
        if installation is None:
            self.java_status_label.setText(self._messages.text("status.java_missing"))
            self.java_status_label.setToolTip(_NO_TOOLTIP)
            return
        self.java_status_label.setText(self._messages.text("status.java_ready", major=installation.major_version))
        self.java_status_label.setToolTip(installation.executable)

    def _set_java_dot(self, ready: bool) -> None:
        self.java_dot.setPixmap(_dot(theme.ACCENT if ready else theme.DANGER))

    def notify(self, message: UserMessage, tone: str = "info") -> None:
        """Queue a notification (M4-GUI-04): success, info, notice (warning) or error."""
        self.notifications.notify(message, tone)

    def notification_texts(self) -> list[str]:
        """Return the texts of every listed notification, shown and waiting."""
        return [render_message(self._messages, item.message) for item in self.notifications.all]

    def _show_error_in_status_bar(self, error: BaseException) -> None:
        self.notify(describe_error(error), "error")

    def _show_message_in_status_bar(self, message: UserMessage) -> None:
        self.notify(message, "success")

    def _show_failure(self, message: UserMessage) -> None:
        if self._guide_is_importing():
            return  # the guide shows it on its import page
        self.notify(message, "error")

    def _on_legacy_imported(self, result: LegacyImportResult) -> None:
        if self._guide_is_importing():
            return  # the guide shows the result on its import page
        self._notify_legacy_result(result)

    def _guide_is_importing(self) -> bool:
        controller = self.first_run_controller
        return controller is not None and controller.state.importing

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
        self.show_page(dialog)

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
        self.show_page(dialog)

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
        dialog.accepted.connect(self._after_settings_saved)
        self.settings_dialog = dialog
        dialog.finished.connect(lambda _result: self._forget_dialog("settings_dialog"))
        self.show_page(dialog)

    # --- language change without a restart (M4-GUI-02) ----------------------------------------

    @property
    def language(self) -> str:
        """Return the language this window shows."""
        return self._messages.language

    def is_busy(self) -> bool:
        """Return whether an operation, a pending automatic restart or an open page would be lost by a rebuild."""
        return bool(
            self.dashboard_controller.busy
            or self.dashboard_controller.has_pending_auto_restart
            or self.creation_controller.busy
            or self.management_controller.busy
            or self.backups_controller.busy
            or self.worlds_controller.busy
            or (self.jar_catalog_controller is not None and self.jar_catalog_controller.state.busy)
            or self.page_host.pages
        )

    def _after_settings_saved(self) -> None:
        settings = self._services.settings
        if settings is None:
            return
        language = resolve_language(settings.current.language, QLocale.system().name())
        theme_setting = settings.current.theme
        if language != self.language or appearance.resolve(theme_setting) != theme.current:
            # Let the Settings page close first; then rebuild if nothing would be lost.
            QTimer.singleShot(0, lambda: self._request_rebuild(language, theme_setting))

    def _request_language(self, language: str) -> None:
        settings = self._services.settings
        self._request_rebuild(language, settings.current.theme if settings is not None else None)

    def _request_rebuild(self, language: str, theme_setting: str | None) -> None:
        """Rebuild the window in ``language`` and the theme ``theme_setting`` means, unless that would lose work."""
        theme_changes = appearance.resolve(theme_setting) != theme.current
        if self.is_busy():
            key = "settings.language.later" if language != self.language else "settings.theme.later"
            self.notify(UserMessage(key), "notice")
            return
        if theme_changes:
            appearance.apply_appearance(theme_setting)
        self.language_change_requested.emit(language)

    def _on_system_color_scheme(self, _scheme: object) -> None:
        """Follow a change of the Windows app mode when the theme setting is Automatic."""
        settings = self._services.settings
        if settings is None or settings.current.theme is not None:
            return
        if appearance.resolve(None) != theme.current:
            QTimer.singleShot(0, lambda: self._request_rebuild(self.language, None))

    def view_state(self) -> tuple[str | None, str]:
        """Return the selected server and the shown tab, to restore them in a rebuilt window."""
        row = self.dashboard_controller.state.row
        return (row.server_id if row is not None else None, self.dashboard_view.current_tab)

    def restore_view_state(self, state: tuple[str | None, str]) -> None:
        """Select the server and tab a previous window showed."""
        server_id, tab = state
        if server_id is not None:
            self.server_list_controller.select(server_id)
        self.dashboard_view.show_tab(tab)

    def release(self) -> None:
        """Stop this window's timers and subscriptions without touching servers (it is being replaced)."""
        self._tear_down()

    def _forget_dialog(self, name: str) -> None:
        dialog = getattr(self, name)
        setattr(self, name, None)
        if dialog is not None:
            dialog.deleteLater()

    def _after_start(self) -> None:
        self.report_unclean_shutdowns()
        if self._first_run_guide and FirstRunController.should_run(self._services.settings, self._server_count()):
            self.open_first_run()
            return
        self.offer_legacy_import()

    # --- first-run guide (M4-GUI-08) ---------------------------------------------------------

    def open_first_run(self) -> None:
        """Open the setup guide as a page (also from File › Setup guide)."""
        if self.first_run_dialog is not None:
            return
        controller = FirstRunController(
            self.management_controller,
            str(self._services.servers_root),
            self._services.java,
            self._services.settings,
            self._server_count,
            self,
        )
        controller.start()
        dialog = FirstRunDialog(
            controller, self._messages, pick_java_with_system_dialog(self._messages), self._open_folder, self
        )
        controller.finished.connect(self._on_first_run_finished)
        dialog.finished.connect(self._forget_first_run)
        self.first_run_controller = controller
        self.first_run_dialog = dialog
        self.show_page(dialog)

    def _server_count(self) -> int:
        return len(self.server_list_controller.state.servers)

    def _on_first_run_finished(self, ending: Ending) -> None:
        self.check_java()  # the guide may have found or chosen Java
        self.server_list_controller.refresh()
        if ending is Ending.CREATE_SERVER:
            QTimer.singleShot(0, self.open_create_dialog)
        elif ending is Ending.IMPORT_FOLDER:
            QTimer.singleShot(0, self.open_adopt_dialog)

    def _forget_first_run(self) -> None:
        dialog, controller = self.first_run_dialog, self.first_run_controller
        self.first_run_dialog = self.first_run_controller = None
        if dialog is not None:
            dialog.deleteLater()
        if controller is not None:
            controller.deleteLater()

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
        text = self._messages.text
        return (
            ask(
                self,
                text("exit.confirm.title"),
                text("exit.confirm.text", server_id=server_id),
                [Choice("cancel", text("dialog.cancel")), Choice("yes", text("exit.confirm.yes"), "primary")],
                tone="warning",
                default="cancel",
            )
            == "yes"
        )

    def _show_delete_dialog(self, configuration: ServerConfiguration, folder: Path) -> bool | None:
        dialog = DeleteServerDialog(configuration, folder, self._messages, self)
        accepted = self.run_page(dialog) == DeleteServerDialog.DialogCode.Accepted
        remove_files = dialog.remove_files
        dialog.deleteLater()
        return remove_files if accepted else None

    def _ask_legacy_import(self, count: int) -> bool:
        text = self._messages.text
        return (
            ask(
                self,
                text("legacy.offer.title"),
                self._messages.plural("legacy.offer.text", count),
                [Choice("no", text("legacy.offer.no")), Choice("yes", text("legacy.offer.yes"), "primary")],
                default="yes",
            )
            == "yes"
        )

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
        ask(
            self,
            self._messages.text("legacy.result.title"),
            text,
            [Choice("ok", self._messages.text("dialog.ok"), "primary")],
        )

    def _ask_to_kill(self, server_id: str) -> bool:
        text = self._messages.text
        return (
            ask(
                self,
                text("kill.confirm.title"),
                text("kill.confirm.text", server_id=server_id),
                [Choice("cancel", text("dialog.cancel")), Choice("yes", text("kill.confirm.yes"), "danger")],
                tone="danger",
                default="cancel",
            )
            == "yes"
        )

    def _ask_to_accept_eula(self, server_id: str) -> bool:
        text = self._messages.text
        return (
            ask(
                self,
                text("eula.title"),
                text("eula.text", server_id=server_id),
                [Choice("cancel", text("dialog.cancel")), Choice("yes", text("eula.accept"), "primary")],
                default="cancel",
            )
            == "yes"
        )

    def _show_java_dialog(self, problem: JavaProblem) -> JavaChoice:
        java = self._services.java
        if java is None:
            return JavaChoice.CANCELLED
        dialog = JavaSetupDialog(problem, java, self._messages, self)
        self.run_page(dialog)
        return dialog.choice

    def _show_unclean_notice(self, incident: UncleanShutdown) -> None:
        text = self._messages.text
        choices = [Choice("ok", text("dialog.ok"), "primary")]
        if self.backups_controller.available:
            choices.insert(0, Choice("backups", text("unclean.open_backups")))
        answer = ask(
            self,
            text("unclean.title", server_id=incident.server_id),
            text("unclean.text", server_id=incident.server_id, started_at=incident.started_at or "?"),
            choices,
            tone="warning",
            default="ok",
        )
        if answer == "backups":
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
        text = self._messages.text
        name = self._server_name(backup.server_id)
        first = ask(
            self,
            text("backups.restore.title", backup_id=backup.backup_id),
            text("backups.restore.text", name=name),
            [Choice("cancel", text("dialog.cancel")), Choice("yes", text("backups.restore.continue"), "primary")],
            tone="warning",
            default="cancel",
        )
        if first != "yes":
            return False
        return (
            ask(
                self,
                text("backups.restore.confirm_title"),
                text("backups.restore.confirm_text", name=name, created_at=format_created_at(backup.created_at)),
                [Choice("cancel", text("dialog.cancel")), Choice("yes", text("backups.restore.yes"), "danger")],
                tone="danger",
                default="cancel",
            )
            == "yes"
        )

    def _ask_to_delete_backup(self, backup: BackupInfo) -> bool:
        text = self._messages.text
        return (
            ask(
                self,
                text("backups.delete.title", backup_id=backup.backup_id),
                text("backups.delete.text"),
                [Choice("cancel", text("dialog.cancel")), Choice("yes", text("dialog.move_to_recycle_bin"), "danger")],
                tone="danger",
                default="cancel",
            )
            == "yes"
        )

    def _ask_after_timeout(self, server_id: str, timeout: float) -> StopTimeoutChoice:
        text = self._messages.text
        answer = ask(
            self,
            text("exit.stop_timed_out.title"),
            text("exit.stop_timed_out.text", server_id=server_id, timeout=f"{timeout:g}"),
            [
                Choice("cancel", text("exit.cancel")),
                Choice("kill", text("exit.kill"), "danger"),
                Choice("wait", text("exit.keep_waiting"), "primary"),
            ],
            tone="warning",
            default="wait",
        )
        if answer == "wait":
            return StopTimeoutChoice.KEEP_WAITING
        if answer == "kill":
            return StopTimeoutChoice.KILL
        return StopTimeoutChoice.CANCEL

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop a running server (after confirmation) before closing; release GUI resources."""
        if not self.page_host.dismiss_all():
            event.ignore()
            self.notify(UserMessage("exit.wait_for_operation"), "notice")
            return
        if (
            self.dashboard_controller.busy
            or self.creation_controller.busy
            or self.management_controller.busy
            or self.backups_controller.busy
            or self.worlds_controller.busy
            or (self.jar_catalog_controller is not None and self.jar_catalog_controller.state.busy)
        ):
            event.ignore()
            self.notify(UserMessage("exit.wait_for_operation"), "notice")
            return
        active = self.dashboard_controller.active_server_id
        if active is not None:
            event.ignore()
            if self._confirm_exit(active) and self.dashboard_controller.stop_active(active):
                self._exit_after_stop = True
                self.notify(UserMessage("exit.stopping", {"server_id": active}), "info")
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
