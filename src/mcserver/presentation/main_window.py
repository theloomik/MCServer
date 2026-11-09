"""Main window shell: menu, placeholder content and status bar."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QWidget

from mcserver.presentation.i18n import Messages
from mcserver.presentation.services import PresentationServices


class MainWindow(QMainWindow):
    """Top-level window. Later stages replace the placeholder with the server list and details.

    The window only reads from ``PresentationServices``; it never builds or
    closes backend services (``app.py`` owns their lifetime).
    """

    def __init__(self, services: PresentationServices, messages: Messages, parent: QWidget | None = None) -> None:
        """Build the window from already-created services and messages."""
        super().__init__(parent)
        self._services = services
        self._messages = messages
        self.setWindowTitle(messages.text("app.title"))
        self.resize(1000, 640)
        self._build_menu()
        self._build_content()
        self._build_status_bar()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(self._messages.text("menu.file"))
        exit_action = file_menu.addAction(self._messages.text("menu.file.exit"))
        exit_action.triggered.connect(self.close)

    def _build_content(self) -> None:
        placeholder = QLabel(self._messages.text("main.placeholder"))
        placeholder.setObjectName("placeholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(placeholder)

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
