"""Main window: server list, selected server details, menu and status bar."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QLabel, QMainWindow, QSplitter, QWidget

from mcserver.presentation.controllers.server_list import ServerListController, ServerListState
from mcserver.presentation.i18n import Messages
from mcserver.presentation.services import PresentationServices
from mcserver.presentation.views.server_details_view import ServerDetailsView
from mcserver.presentation.views.server_list_view import ServerListView


class MainWindow(QMainWindow):
    """Top-level window that wires the server list controller to its views.

    The window only reads from ``PresentationServices``; it never builds or
    closes backend services (``app.py`` owns their lifetime).
    """

    def __init__(self, services: PresentationServices, messages: Messages, parent: QWidget | None = None) -> None:
        """Build the window from already-created services and messages, then load the servers."""
        super().__init__(parent)
        self._services = services
        self._messages = messages
        self.setWindowTitle(messages.text("app.title"))
        self.resize(1000, 640)

        self.server_list_controller = ServerListController(services.management, services.coordinator, self)
        self.server_list_view = ServerListView(messages)
        self.server_details_view = ServerDetailsView(messages, services.servers_root)

        self._build_menu()
        self._build_content()
        self._build_status_bar()
        self._connect()
        self.server_list_controller.refresh()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(self._messages.text("menu.file"))
        self.refresh_action = file_menu.addAction(self._messages.text("menu.file.refresh"))
        self.refresh_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Refresh))
        file_menu.addSeparator()
        self.exit_action = file_menu.addAction(self._messages.text("menu.file.exit"))
        self.exit_action.triggered.connect(self.close)

    def _build_content(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        splitter.addWidget(self.server_list_view)
        splitter.addWidget(self.server_details_view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setChildrenCollapsible(False)
        self.server_list_view.setMinimumWidth(220)
        self.setCentralWidget(splitter)

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
        controller = self.server_list_controller
        controller.state_changed.connect(self._show_state)
        self.server_list_view.server_selected.connect(controller.select)
        self.server_list_view.refresh_requested.connect(controller.refresh)
        self.refresh_action.triggered.connect(controller.refresh)

    def _show_state(self, state: ServerListState) -> None:
        self.server_list_view.show_state(state)
        self.server_details_view.show_state(state)
