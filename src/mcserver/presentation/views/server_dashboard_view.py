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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mcserver.application.server_activity import ServerActivitySnapshot
from mcserver.application.server_address import ServerAddress
from mcserver.application.server_metrics import ServerMetricsSnapshot
from mcserver.presentation.controllers.server_dashboard import DashboardState, Operation
from mcserver.presentation.controllers.server_list import ServerStatus
from mcserver.presentation.errors import UserMessage, render_message
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.server_console_view import ServerConsoleView
from mcserver.presentation.views.status_text import STATUS_KEYS

INFO_FIELDS = ("directory", "location", "jar_file", "memory")
"""Rows of the information card; each has the label key ``server_details.field.<name>``."""

_SIDE_PANEL_WIDTH = 300
_INFO_VALUE_WIDTH = _SIDE_PANEL_WIDTH - 60  # card margins and border
_NO_TOOLTIP = ""
METRIC_TILES = ("cpu", "memory", "uptime", "players", "tps")
"""Resource tiles; each has the label key ``metrics.<name>``."""


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
    kill_requested = Signal()
    restart_requested = Signal()
    edit_requested = Signal()
    delete_requested = Signal()
    details_requested = Signal(object)  # UserMessage
    open_folder_requested = Signal(object)  # Path
    open_logs_requested = Signal(object)  # Path
    copy_address_requested = Signal(str)

    def __init__(self, messages: Messages, servers_root: Path, console_available: bool) -> None:
        """Build the dashboard for servers inside ``servers_root``."""
        super().__init__()
        self._messages = messages
        self._servers_root = servers_root
        self._folder: Path | None = None
        self._banner_message: UserMessage | None = None

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
        # Overview holds the console; Properties and Backups are added by the window when available (M3).
        self.tabs = QTabWidget()
        self.tabs.setObjectName("dashboardTabs")
        self.tabs.setDocumentMode(True)
        self._tab_keys: list[str] = []
        self.add_tab("overview", self.console)
        main.addWidget(self.tabs, 1)

        side = QVBoxLayout()
        side.setSpacing(12)
        caption = QLabel(self._messages.text("dashboard.info.title").upper())
        caption.setObjectName("sectionCaption")
        side.addWidget(caption)
        side.addWidget(self._build_info_card())
        self.metrics_caption = QLabel(self._messages.text("metrics.title").upper())
        self.metrics_caption.setObjectName("sectionCaption")
        self.metrics_card = self._build_metrics_card()
        self.metrics_caption.hide()
        self.metrics_card.hide()
        side.addWidget(self.metrics_caption)
        side.addWidget(self.metrics_card)
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
        self.kill_button = QPushButton(self._messages.text("dashboard.kill"))
        self.kill_button.setObjectName("killButton")
        self.kill_button.clicked.connect(self.kill_requested)
        self.kill_button.hide()
        self.restart_button = QPushButton(self._messages.text("dashboard.restart"))
        self.restart_button.setObjectName("secondaryButton")
        self.restart_button.clicked.connect(self.restart_requested)
        self.restart_button.hide()
        for button in (self.start_button, self.stop_button, self.kill_button, self.restart_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumWidth(150)
        self.hint_label = QLabel()
        self.hint_label.setObjectName("controlHint")
        self.hint_label.setWordWrap(True)
        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.kill_button)
        controls.addWidget(self.restart_button)
        controls.addStretch(1)

        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_button = QPushButton(self._messages.text("dashboard.details"))
        self.details_button.setObjectName("detailsButton")
        self.details_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.details_button.clicked.connect(self._on_details)
        banner_row = QHBoxLayout()
        banner_row.setSpacing(10)
        banner_row.addWidget(self.banner, 1)
        banner_row.addWidget(self.details_button, 0, Qt.AlignmentFlag.AlignTop)
        self.banner_row = QWidget()
        self.banner_row.setLayout(banner_row)
        banner_row.setContentsMargins(0, 0, 0, 0)
        self.banner.hide()
        self.banner_row.hide()
        self.details_button.hide()

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addLayout(title_row)
        layout.addLayout(controls)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.banner_row)
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
        self.open_logs_button = QPushButton(self._messages.text("dashboard.open_logs"))
        self.open_logs_button.setObjectName("secondaryButton")
        self.open_logs_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_logs_button.clicked.connect(self._on_open_logs)
        address_label = QLabel(self._messages.text("dashboard.address"))
        address_label.setObjectName("fieldLabel")
        self.address_value = QLabel()
        self.address_value.setObjectName("fieldValue")
        self.address_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.copy_address_button = QPushButton(self._messages.text("dashboard.copy_address"))
        self.copy_address_button.setObjectName("clearConsole")
        self.copy_address_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_address_button.clicked.connect(self._on_copy_address)
        address_row = QHBoxLayout()
        address_row.addWidget(self.address_value, 1)
        address_row.addWidget(self.copy_address_button)
        grid.addWidget(address_label, len(INFO_FIELDS) * 2, 0)
        grid.addLayout(address_row, len(INFO_FIELDS) * 2 + 1, 0)
        self._address: ServerAddress | None = None
        self.show_address(None)
        self.edit_button = QPushButton(self._messages.text("dashboard.edit"))
        self.edit_button.setObjectName("secondaryButton")
        self.edit_button.clicked.connect(self.edit_requested)
        self.delete_button = QPushButton(self._messages.text("dashboard.delete"))
        self.delete_button.setObjectName("secondaryButton")
        self.delete_button.clicked.connect(self.delete_requested)
        manage_row = QHBoxLayout()
        manage_row.setSpacing(8)
        for button in (self.edit_button, self.delete_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            manage_row.addWidget(button)
        note = QLabel(self._messages.text("server_details.next_launch_note"))
        note.setObjectName("controlHint")
        note.setWordWrap(True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        layout.addLayout(grid)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        folder_row.addWidget(self.open_folder_button)
        folder_row.addWidget(self.open_logs_button)
        layout.addLayout(folder_row)
        layout.addLayout(manage_row)
        layout.addWidget(note)
        return card

    def _build_metrics_card(self) -> QFrame:
        card = _card()
        card.setObjectName("metricsCard")
        grid = QGridLayout(card)
        grid.setContentsMargins(20, 14, 20, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        self.metric_values: dict[str, QLabel] = {}
        grid.setVerticalSpacing(8)
        for row, name in enumerate(METRIC_TILES):
            label = QLabel(self._messages.text(f"metrics.{name}"))
            label.setObjectName("fieldLabel")
            value = QLabel(self._messages.text("metrics.idle"))
            value.setObjectName("metricValue")
            self.metric_values[name] = value
            grid.addWidget(label, row, 0)
            grid.addWidget(value, row, 1, Qt.AlignmentFlag.AlignRight)
        return card

    def add_tab(self, key: str, widget: QWidget) -> None:
        """Add a main-column tab titled ``tabs.<key>``."""
        self._tab_keys.append(key)
        self.tabs.addTab(widget, self._messages.text(f"tabs.{key}"))

    def show_tab(self, key: str) -> None:
        """Switch to the tab ``key`` if it exists."""
        if key in self._tab_keys:
            self.tabs.setCurrentIndex(self._tab_keys.index(key))

    @property
    def current_tab(self) -> str:
        """Return the key of the shown tab."""
        return self._tab_keys[self.tabs.currentIndex()]

    def set_metrics_available(self, available: bool) -> None:
        """Show the resource tiles (only when metrics can be read at all)."""
        self.metrics_caption.setVisible(available)
        self.metrics_card.setVisible(available)

    def show_address(self, address: ServerAddress | None) -> None:
        """Show where LAN players connect (``None`` when it is not known)."""
        self._address = address
        self.address_value.setText(str(address) if address else self._messages.text("dashboard.address_unknown"))
        self.copy_address_button.setEnabled(address is not None)

    def show_activity(self, snapshot: ServerActivitySnapshot | None) -> None:
        """Show players online and tick rate of the running server, or dashes."""
        players, tps = self.metric_values["players"], self.metric_values["tps"]
        idle = self._messages.text("metrics.idle")
        if snapshot is None:
            players.setText(idle)
            players.setToolTip(_NO_TOOLTIP)
            tps.setText(idle)
            return
        maximum = snapshot.max_players
        players.setText(
            self._messages.text("metrics.players_value", count=snapshot.player_count, maximum=maximum)
            if maximum is not None
            else str(snapshot.player_count)
        )
        players.setToolTip(self._messages.text("metrics.players_names", names=", ".join(snapshot.players)))
        tps.setText(
            self._messages.text("metrics.tps_value", tps=f"{snapshot.tps:.1f}") if snapshot.tps is not None else idle
        )

    def show_metrics(self, snapshot: ServerMetricsSnapshot | None) -> None:
        """Show CPU, memory and uptime of the selected server, or dashes when it does not run."""
        if snapshot is None:
            for name in ("cpu", "memory", "uptime"):
                value = self.metric_values[name]
                value.setText(self._messages.text("metrics.idle"))
            return
        text = self._messages.text
        self.metric_values["cpu"].setText(text("metrics.cpu_value", percent=f"{snapshot.cpu_percent:.0f}"))
        self.metric_values["memory"].setText(
            text("metrics.memory_value", used=f"{snapshot.memory_mb:.0f}", allocated=snapshot.allocated_mb)
        )
        hours, rest = divmod(max(0, snapshot.uptime_seconds), 3600)
        minutes, seconds = divmod(rest, 60)
        self.metric_values["uptime"].setText(
            text("metrics.uptime_value", hours=hours, minutes=minutes, seconds=seconds)
        )

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
        self.title_label.setText(configuration.name)
        self.title_label.setToolTip(configuration.server_id)
        # Deleting is only possible while this server is not active (M2-GUI-04).
        self.delete_button.setEnabled(state.status in (ServerStatus.STOPPED, ServerStatus.UNKNOWN))
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
        self.kill_button.setVisible(state.can_kill or state.operation is Operation.KILLING)
        self.kill_button.setEnabled(state.can_kill)
        starting = state.operation is Operation.STARTING or state.status is ServerStatus.STARTING
        stopping = state.operation is Operation.STOPPING
        killing = state.operation is Operation.KILLING
        restarting = state.operation is Operation.RESTARTING
        self.restart_button.setVisible(state.can_restart or restarting)
        self.restart_button.setEnabled(state.can_restart)
        self.restart_button.setText(self._messages.text("dashboard.restarting" if restarting else "dashboard.restart"))
        self.start_button.setText(self._messages.text("dashboard.starting" if starting else "dashboard.start"))
        self.stop_button.setText(self._messages.text("dashboard.stopping" if stopping else "dashboard.stop"))
        self.kill_button.setText(self._messages.text("dashboard.killing" if killing else "dashboard.kill"))
        self.console.set_input_enabled(state.can_send_command)
        self.hint_label.setText(self._hint(state))
        if state.error is not None:
            self._show_banner(state.error, "error")
        elif state.notice is not None:
            self._show_banner(state.notice, "notice")
        else:
            self._show_banner(state.success, "success")
        self.pages.setCurrentWidget(self.dashboard_page)

    def _hint(self, state: DashboardState) -> str:
        if state.hint is not None:
            return render_message(self._messages, state.hint)
        if not state.java_available:
            return self._messages.text("dashboard.hint.java_missing")
        if state.other_active_server is not None:
            return self._messages.text("dashboard.hint.other_running", server_id=state.other_active_server)
        if state.stop_timed_out and state.row is not None:
            return self._messages.text("dashboard.hint.stop_timed_out", server_id=state.row.server_id)
        if state.status is ServerStatus.STARTING:
            return self._messages.text("dashboard.hint.starting")
        if state.status is ServerStatus.STOPPING:
            return self._messages.text("dashboard.hint.stopping")
        if state.status is ServerStatus.RUNNING and state.operation is None:
            return self._messages.text("dashboard.hint.running")
        return ""

    def _show_banner(self, message: UserMessage | None, tone: str) -> None:
        self._banner_message = message
        if message is None:
            self.banner.hide()  # its tooltip is replaced whenever it is shown again
            self.banner_row.hide()
            return
        self.banner.setText(render_message(self._messages, message))
        self.banner.setToolTip(message.details)
        self.banner.setProperty("tone", tone)
        _repolish(self.banner)
        self.details_button.setVisible(bool(message.details))
        self.banner.show()
        self.banner_row.show()

    def _on_details(self) -> None:
        if self._banner_message is not None:
            self.details_requested.emit(self._banner_message)

    def _on_open_logs(self) -> None:
        if self._folder is not None:
            self.open_logs_requested.emit(self._folder / "logs")

    def _on_copy_address(self) -> None:
        if self._address is not None:
            self.copy_address_requested.emit(str(self._address))

    def _on_open_folder(self) -> None:
        if self._folder is not None:
            self.open_folder_requested.emit(self._folder)
