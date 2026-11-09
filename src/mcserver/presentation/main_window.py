"""Main window: sidebar with servers, dashboard for the selected server, menu and status bar."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QMessageBox, QWidget

from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.presentation import theme
from mcserver.presentation.adapters.output_bridge import OutputBridge
from mcserver.presentation.adapters.status_poller import StatusPoller
from mcserver.presentation.controllers.console import ConsoleController
from mcserver.presentation.controllers.server_creation import ServerCreationController
from mcserver.presentation.controllers.server_dashboard import ServerDashboardController
from mcserver.presentation.controllers.server_list import ServerListController, ServerListState
from mcserver.presentation.dialogs.create_server_dialog import CreateServerDialog
from mcserver.presentation.i18n import Messages
from mcserver.presentation.services import PresentationServices
from mcserver.presentation.views.server_dashboard_view import ServerDashboardView
from mcserver.presentation.views.server_list_view import ServerListView
from mcserver.presentation.workers import BackgroundRunner

ConfirmExit = Callable[[str], bool]
FolderOpener = Callable[[Path], bool]
CreateDialogFactory = Callable[[ServerCreationController, Messages, QWidget], CreateServerDialog]


def open_folder_with_system(path: Path) -> bool:
    """Open ``path`` in the system file manager; return whether it worked."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class MainWindow(QMainWindow):
    """Top-level window: builds controllers and views from services and wires them together.

    The window never builds or closes backend services (``app.py`` owns them).
    Closing it while a server runs asks for confirmation, stops the server in
    the background and closes once the stop has finished.
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
    ) -> None:
        """Build the window from already-created services and messages, then load the servers."""
        super().__init__(parent)
        self._services = services
        self._messages = messages
        self._confirm_exit = confirm_exit or self._ask_to_stop_and_exit
        self._open_folder = open_folder
        self._create_dialog_factory = create_dialog
        self.create_dialog: CreateServerDialog | None = None
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
        self.dashboard_controller = ServerDashboardController(coordinator, self.poller, self.background, self)
        self.console_controller = ConsoleController(self.output_bridge, parent=self)
        # Creation needs no Java: it is available in configuration-only mode as well.
        self.creation_controller = ServerCreationController(
            services.server_creation, services.management, self.background, self
        )

        self.server_list_view = ServerListView(messages)
        self.dashboard_view = ServerDashboardView(messages, services.servers_root, self.console_controller.available)

        self._build_menu()
        self._build_content()
        self._build_status_bar()
        self._connect()
        if self.poller is not None:
            self.poller.start()
        self.server_list_controller.refresh()

    # --- construction ---------------------------------------------------------------------

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(self._messages.text("menu.file"))
        self.new_server_action = file_menu.addAction(self._messages.text("menu.file.new_server"))
        self.new_server_action.setShortcut(QKeySequence(QKeySequence.StandardKey.New))
        self.refresh_action = file_menu.addAction(self._messages.text("menu.file.refresh"))
        self.refresh_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Refresh))
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
        if self._services.can_run_servers:
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
        dashboard.operation_finished.connect(self._on_operation_finished)
        self.dashboard_view.start_requested.connect(dashboard.start)
        self.dashboard_view.stop_requested.connect(dashboard.stop)
        self.dashboard_view.open_folder_requested.connect(self._open_server_folder)

        console = self.console_controller
        console.lines_appended.connect(self.dashboard_view.console.append_lines)
        console.cleared.connect(self.dashboard_view.console.clear)
        self.dashboard_view.console.clear_requested.connect(console.clear)

    # --- behaviour --------------------------------------------------------------------------

    def _show_list_state(self, state: ServerListState) -> None:
        self.server_list_view.show_state(state)
        self.dashboard_controller.show_server(state.selected)
        self.dashboard_view.show_details_error(state.details_error_key)
        self.console_controller.show_server(state.selected.server_id if state.selected else None)

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

    def _ask_to_stop_and_exit(self, server_id: str) -> bool:
        answer = QMessageBox.question(
            self,
            self._messages.text("exit.confirm.title"),
            self._messages.text("exit.confirm.text", server_id=server_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _on_operation_finished(self) -> None:
        if self._exit_after_stop:
            self._exit_after_stop = False
            self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop a running server (after confirmation) before closing; release GUI resources."""
        if self.dashboard_controller.busy or self.creation_controller.busy:
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
        self.console_controller.close()
        self.background.dispose()
