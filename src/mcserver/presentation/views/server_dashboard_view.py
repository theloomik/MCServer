"""Central dashboard: server card with controls, console and an information panel."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mcserver.presentation.controllers.server_dashboard import DashboardState, Operation
from mcserver.presentation.controllers.server_list import ServerStatus
from mcserver.presentation.errors import UserMessage
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.server_console_view import ServerConsoleView
from mcserver.presentation.views.status_text import STATUS_KEYS

INFO_FIELDS = ("directory", "location", "jar_file", "memory")
"""Rows of the information card; each has the label key ``server_details.field.<name>``."""

_SIDE_PANEL_WIDTH = 300
_INFO_VALUE_WIDTH = _SIDE_PANEL_WIDTH - 60  # card margins and border


def _card() -> QFrame:
    frame = QFrame()
    frame.setProperty("card", True)
    return frame


def _repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property change."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


class ServerDashboardView(QWidget):
    """Render ``DashboardState``; emits user intents and never calls the backend."""

    start_requested = Signal()
    stop_requested = Signal()
    open_folder_requested = Signal(object)  # Path

    def __init__(self, messages: Messages, servers_root: Path, console_available: bool) -> None:
        """Build the dashboard for servers inside ``servers_root``."""
        super().__init__()
        self._messages = messages
        self._servers_root = servers_root
        self._folder: Path | None = None

        self.welcome_page = self._build_welcome()
        self.console = ServerConsoleView(messages, console_available)
        self.dashboard_page = self._build_dashboard()

        self.pages = QStackedWidget()
        self.pages.addWidget(self.welcome_page)
        self.pages.addWidget(self.dashboard_page)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.pages)
        self.pages.setCurrentWidget(self.welcome_page)

    # --- construction ---------------------------------------------------------------------

    def _build_welcome(self) -> QWidget:
        page = QWidget()
        title = QLabel(self._messages.text("welcome.title"))
        title.setObjectName("welcomeTitle")
        self.welcome_text = QLabel(self._messages.text("welcome.text"))
        self.welcome_text.setObjectName("welcomeText")
        self.welcome_text.setWordWrap(True)
        for label in (title, self.welcome_text):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(page)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(self.welcome_text)
        layout.addStretch(1)
        return page

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        main = QVBoxLayout()
        main.setSpacing(18)
        main.addWidget(self._build_header_card())
        main.addWidget(self.console, 1)

        side = QVBoxLayout()
        side.setSpacing(12)
        caption = QLabel(self._messages.text("dashboard.info.title").upper())
        caption.setObjectName("sectionCaption")
        side.addWidget(caption)
        side.addWidget(self._build_info_card())
        side.addStretch(1)
        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(_SIDE_PANEL_WIDTH)

        layout = QHBoxLayout(page)
        layout.setContentsMargins(28, 24, 24, 20)
        layout.setSpacing(22)
        layout.addLayout(main, 1)
        layout.addWidget(side_widget)
        return page

    def _build_header_card(self) -> QFrame:
        card = _card()
        card.setObjectName("headerCard")
        self.title_label = QLabel()
        self.title_label.setObjectName("serverTitle")
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("serverSubtitle")
        self.status_pill = QLabel()
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_row = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        title_row.addLayout(titles, 1)
        title_row.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignTop)

        self.start_button = QPushButton(self._messages.text("dashboard.start"))
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self.start_requested)
        self.stop_button = QPushButton(self._messages.text("dashboard.stop"))
        self.stop_button.setObjectName("stopButton")
        self.stop_button.clicked.connect(self.stop_requested)
        for button in (self.start_button, self.stop_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumWidth(150)
        self.hint_label = QLabel()
        self.hint_label.setObjectName("controlHint")
        self.hint_label.setWordWrap(True)
        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addSpacing(8)
        controls.addWidget(self.hint_label, 1)

        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.banner.hide()

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addLayout(title_row)
        layout.addLayout(controls)
        layout.addWidget(self.banner)
        return card

    def _build_info_card(self) -> QFrame:
        card = _card()
        card.setObjectName("infoCard")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self.info_values: dict[str, QLabel] = {}
        for row, field in enumerate(INFO_FIELDS):
            label = QLabel(self._messages.text(f"server_details.field.{field}"))
            label.setObjectName("fieldLabel")
            value = QLabel()
            value.setObjectName("fieldValue")
            value.setWordWrap(field != "location")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.info_values[field] = value
            grid.addWidget(label, row * 2, 0)
            grid.addWidget(value, row * 2 + 1, 0)
        self.open_folder_button = QPushButton(self._messages.text("dashboard.open_folder"))
        self.open_folder_button.setObjectName("openFolderButton")
        self.open_folder_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_folder_button.clicked.connect(self._on_open_folder)
        note = QLabel(self._messages.text("server_details.next_launch_note"))
        note.setObjectName("controlHint")
        note.setWordWrap(True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        layout.addLayout(grid)
        layout.addWidget(self.open_folder_button)
        layout.addWidget(note)
        return card

    # --- rendering ------------------------------------------------------------------------

    def show_details_error(self, key: str | None) -> None:
        """Show a details error on the welcome page (selected server missing or unreadable)."""
        self.welcome_text.setText(self._messages.text(key or "welcome.text"))

    def show_state(self, state: DashboardState) -> None:
        """Render the selected server, or the welcome page when nothing is selected."""
        row = state.row
        if row is None:
            self.pages.setCurrentWidget(self.welcome_page)
            return
        self.welcome_text.setText(self._messages.text("welcome.text"))
        configuration = row.configuration
        memory = self._messages.text("server_details.memory_value", memory_mb=configuration.memory_mb)
        self._folder = self._servers_root / configuration.directory
        self.title_label.setText(configuration.server_id)
        self.subtitle_label.setText(
            self._messages.text("dashboard.subtitle", jar_file=configuration.jar_file, memory=memory)
        )
        self.info_values["directory"].setText(configuration.directory)
        location = self.info_values["location"]
        location.setToolTip(str(self._folder))
        location.setText(
            location.fontMetrics().elidedText(str(self._folder), Qt.TextElideMode.ElideMiddle, _INFO_VALUE_WIDTH)
        )
        self.info_values["jar_file"].setText(configuration.jar_file)
        self.info_values["memory"].setText(memory)

        self.status_pill.setText(self._messages.text(STATUS_KEYS[state.status]).upper())
        self.status_pill.setProperty("status", state.status.value)
        _repolish(self.status_pill)

        self.start_button.setEnabled(state.can_start)
        self.stop_button.setEnabled(state.can_stop)
        starting = state.operation is Operation.STARTING
        stopping = state.operation is Operation.STOPPING
        self.start_button.setText(self._messages.text("dashboard.starting" if starting else "dashboard.start"))
        self.stop_button.setText(self._messages.text("dashboard.stopping" if stopping else "dashboard.stop"))
        self.hint_label.setText(self._hint(state))
        if state.error is not None:
            self._show_banner(state.error, "error")
        else:
            self._show_banner(state.notice, "notice")
        self.pages.setCurrentWidget(self.dashboard_page)

    def _hint(self, state: DashboardState) -> str:
        if not state.java_available:
            return self._messages.text("dashboard.hint.java_missing")
        if state.other_active_server is not None:
            return self._messages.text("dashboard.hint.other_running", server_id=state.other_active_server)
        if state.status is ServerStatus.RUNNING and state.operation is None:
            return self._messages.text("dashboard.hint.running")
        return ""

    def _show_banner(self, message: UserMessage | None, tone: str) -> None:
        if message is None:
            self.banner.hide()  # its tooltip is replaced whenever it is shown again
            return
        self.banner.setText(self._messages.text(message.key, **message.params))
        self.banner.setToolTip(message.details)
        self.banner.setProperty("tone", tone)
        _repolish(self.banner)
        self.banner.show()

    def _on_open_folder(self) -> None:
        if self._folder is not None:
            self.open_folder_requested.emit(self._folder)
