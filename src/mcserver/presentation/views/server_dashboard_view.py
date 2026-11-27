"""Central dashboard (M4 design): server header with actions, hint, banner, tabs; Overview = console + inspector."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mcserver.application.server_activity import ServerActivitySnapshot
from mcserver.application.server_address import ServerAddress
from mcserver.application.server_metrics import ServerMetricsSnapshot
from mcserver.presentation import icons, theme
from mcserver.presentation.controllers.server_dashboard import DashboardState, Operation
from mcserver.presentation.controllers.server_list import ServerStatus
from mcserver.presentation.errors import UserMessage, render_message
from mcserver.presentation.i18n import Messages
from mcserver.presentation.metrics_history import HISTORY_CAPACITY, MetricPoint
from mcserver.presentation.views.charts import Sparkline
from mcserver.presentation.views.server_console_view import ServerConsoleView
from mcserver.presentation.views.status_text import STATUS_KEYS
from mcserver.presentation.views.widgets import (
    Banner,
    MetricRow,
    WrapRow,
    button,
    caption,
    card,
    icon_button,
    repolish,
)

INFO_FIELDS = ("directory", "location", "jar_file", "memory")
"""Rows of the server card; each has the label key ``server_details.field.<name>``."""

INSPECTOR_WIDTH = 284
_INFO_VALUE_WIDTH = 150  # value column next to the labels
_NO_TOOLTIP = ""
METRIC_TILES = ("cpu", "memory", "uptime", "players", "tps")
"""Resource rows; each has the label key ``metrics.<name>``."""
_CHART_COLORS = {"cpu": "ACCENT", "memory": "INFO"}
"""Metrics with a history chart, and the theme colour of each."""
METRICS_SAMPLE_SECONDS = 2
"""How often the window samples metrics (``main_window.METRICS_INTERVAL_MS``)."""


class _Overview(QWidget):
    """Console beside the inspector; below it when the window is narrow (125 %/150 % scaling, M4-GUI-07)."""

    STACKED_INSPECTOR_HEIGHT = 240
    STACKED_INSPECTOR_MINIMUM = 100
    """Below the console the inspector scrolls; in a short window it keeps at least this much."""

    def __init__(self, console: QWidget, inspector: QScrollArea) -> None:
        super().__init__()
        self.console = console
        self.inspector = inspector
        self.layout_ = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(16)
        self.layout_.addWidget(console, 1)
        self.layout_.addWidget(inspector)
        self._side_by_side(True)

    @property
    def stacked(self) -> bool:
        """Return whether the inspector is below the console."""
        return self.layout_.direction() is QBoxLayout.Direction.TopToBottom

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        """Need only what the stacked layout needs, so the window can be narrow."""
        console = self.console.minimumSizeHint()
        return QSize(console.width(), console.height() + self.STACKED_INSPECTOR_MINIMUM + self.layout_.spacing())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        """Put the inspector beside the console only when both fit."""
        wide = event.size().width() >= self.console.minimumSizeHint().width() + INSPECTOR_WIDTH + 16
        if wide == self.stacked:
            self._side_by_side(wide)
        super().resizeEvent(event)

    def _side_by_side(self, wide: bool) -> None:
        inspector = self.inspector
        if wide:
            self.layout_.setDirection(QBoxLayout.Direction.LeftToRight)
            inspector.setMinimumHeight(0)
            inspector.setMaximumHeight(16777215)
            inspector.setFixedWidth(INSPECTOR_WIDTH)
        else:
            self.layout_.setDirection(QBoxLayout.Direction.TopToBottom)
            inspector.setMinimumWidth(0)
            inspector.setMaximumWidth(16777215)
            inspector.setMinimumHeight(self.STACKED_INSPECTOR_MINIMUM)
            inspector.setMaximumHeight(self.STACKED_INSPECTOR_HEIGHT)


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
    new_server_requested = Signal()
    import_requested = Signal()

    def __init__(self, messages: Messages, servers_root: Path, console_available: bool) -> None:
        """Build the dashboard for servers inside ``servers_root``."""
        super().__init__()
        self._messages = messages
        self._servers_root = servers_root
        self._folder: Path | None = None
        self._banner_message: UserMessage | None = None
        self._address: ServerAddress | None = None

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
        tile = QLabel()
        tile.setObjectName("iconTile")
        tile.setProperty("tone", "accent")
        tile.setFixedSize(58, 58)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setPixmap(icons.pixmap("server", theme.ACCENT_HOVER, 28))
        title = QLabel(self._messages.text("welcome.title"))
        title.setObjectName("welcomeTitle")
        self.welcome_text = QLabel(self._messages.text("welcome.text"))
        self.welcome_text.setObjectName("welcomeText")
        self.welcome_text.setWordWrap(True)
        self.welcome_text.setFixedWidth(440)
        for label in (title, self.welcome_text):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_new_button = button(self._messages.text("server_list.create"), "primary", "plus")
        self.welcome_new_button.clicked.connect(self.new_server_requested)
        self.welcome_import_button = button(self._messages.text("server_list.import"), "secondary", "import")
        self.welcome_import_button.clicked.connect(self.import_requested)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch(1)
        actions.addWidget(self.welcome_new_button)
        actions.addWidget(self.welcome_import_button)
        actions.addStretch(1)
        legacy = QLabel(self._messages.text("welcome.legacy"))
        legacy.setObjectName("welcomeLegacy")
        legacy.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        layout.addStretch(1)
        layout.addWidget(tile, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)
        layout.addWidget(self.welcome_text, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(4)
        layout.addLayout(actions)
        layout.addSpacing(6)
        layout.addWidget(legacy)
        layout.addStretch(1)
        return page

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(14)
        layout.addLayout(self._build_header())
        self.hint_row = QWidget()
        hint_layout = QHBoxLayout(self.hint_row)
        hint_layout.setContentsMargins(0, 0, 0, 0)
        hint_layout.setSpacing(6)
        self.hint_icon = QLabel()
        self.hint_icon.setFixedSize(14, 14)
        self.hint_label = QLabel()
        self.hint_label.setObjectName("controlHint")
        self.hint_label.setWordWrap(True)
        hint_layout.addWidget(self.hint_icon, 0, Qt.AlignmentFlag.AlignTop)
        hint_layout.addWidget(self.hint_label, 1)
        layout.addWidget(self.hint_row)

        self.banner_row = Banner(self._messages.text("dashboard.details"))
        self.banner = self.banner_row.text
        self.details_button = self.banner_row.action
        self.details_button.setObjectName("detailsButton")
        self.details_button.clicked.connect(self._on_details)
        layout.addWidget(self.banner_row)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("dashboardTabs")
        self.tabs.setDocumentMode(True)
        self._tab_keys: list[str] = []
        self.inspector = self._build_inspector()
        self.overview = _Overview(self.console, self.inspector)
        self.add_tab("overview", self.overview)
        layout.addWidget(self.tabs, 1)
        return page

    def _build_header(self) -> QHBoxLayout:
        self.title_label = QLabel()
        self.title_label.setObjectName("serverTitle")
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status_pill = QLabel()
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("serverSubtitle")
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.addWidget(self.title_label)
        title_row.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addLayout(title_row)
        titles.addWidget(self.subtitle_label)

        text = self._messages.text
        self.start_button = button(text("dashboard.start"), "primary", "play", "startButton")
        self.start_button.clicked.connect(self.start_requested)
        self.stop_button = button(text("dashboard.stop"), "secondary", "stop", "stopButton")
        self.stop_button.clicked.connect(self.stop_requested)
        self.restart_button = button(text("dashboard.restart"), "secondary", "restart")
        self.restart_button.clicked.connect(self.restart_requested)
        self.kill_button = button(text("dashboard.kill"), "danger", "kill", "killButton")
        self.kill_button.clicked.connect(self.kill_requested)
        self.kill_button.hide()
        controls = QHBoxLayout()
        controls.setSpacing(8)
        for widget in (self.start_button, self.stop_button, self.restart_button, self.kill_button):
            controls.addWidget(widget)

        header = QHBoxLayout()
        header.setSpacing(16)
        header.addLayout(titles, 1)
        header.addLayout(controls)
        return header

    def _build_inspector(self) -> QScrollArea:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.metrics_card = self._build_metrics_card()
        layout.addWidget(self.metrics_card)
        layout.addWidget(self._build_info_card())
        layout.addStretch(1)
        # Small windows scroll the inspector instead of squeezing its rows.
        scroll = QScrollArea()
        scroll.setWidget(column)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(INSPECTOR_WIDTH)
        return scroll

    def _build_metrics_card(self) -> QFrame:
        frame = card("metricsCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        head = QHBoxLayout()
        self.metrics_caption = caption(self._messages.text("metrics.title"))
        self.live_label = QLabel(self._messages.text("metrics.not_running"))
        self.live_label.setObjectName("panelCount")
        head.addWidget(self.metrics_caption, 1)
        head.addWidget(self.live_label)
        layout.addLayout(head)
        self.metric_rows: dict[str, MetricRow] = {}
        self.metric_values: dict[str, QLabel] = {}
        idle = self._messages.text("metrics.idle")
        self.charts: dict[str, Sparkline] = {}
        for name in METRIC_TILES:
            row = MetricRow(self._messages.text(f"metrics.{name}"), idle)
            self.metric_rows[name] = row
            self.metric_values[name] = row.value
            layout.addWidget(row)
            if name in _CHART_COLORS:
                # History instead of a bar: the last ten minutes, newest on the right (M4-GUI-06).
                chart = Sparkline(_CHART_COLORS[name], HISTORY_CAPACITY)
                chart.setAccessibleName(self._messages.text(f"metrics.{name}"))
                self.charts[name] = chart
                layout.addWidget(chart)
        self.history_caption = QLabel(
            self._messages.text("metrics.history_span", minutes=HISTORY_CAPACITY * METRICS_SAMPLE_SECONDS // 60)
        )
        self.history_caption.setObjectName("panelCount")
        layout.addWidget(self.history_caption)
        self.show_history((), live=False)
        self.players_label = QLabel()
        self.players_label.setObjectName("fieldLabel")
        self.players_label.setWordWrap(True)
        self.players_label.hide()
        layout.addWidget(self.players_label)
        return frame

    def _build_info_card(self) -> QFrame:
        frame = card("infoCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(caption(self._messages.text("dashboard.info.title")))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        self.info_values: dict[str, QLabel] = {}
        for row, field in enumerate(INFO_FIELDS):
            label = QLabel(self._messages.text(f"server_details.field.{field}"))
            label.setObjectName("fieldLabel")
            value = QLabel()
            value.setObjectName("fieldValue")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            # Long names never widen the card; the tooltip shows the whole value.
            value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self.info_values[field] = value
            grid.addWidget(label, row, 0)
            grid.addWidget(value, row, 1)

        address_label = QLabel(self._messages.text("dashboard.address"))
        address_label.setObjectName("fieldLabel")
        self.address_value = QLabel()
        self.address_value.setObjectName("fieldValue")
        self.address_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.address_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.address_value.setWordWrap(True)  # "no network" texts are long in some languages
        self.copy_address_button = icon_button("copy", self._messages.text("dashboard.copy_address"))
        self.copy_address_button.clicked.connect(self._on_copy_address)
        address_value_row = QHBoxLayout()
        address_value_row.setSpacing(2)
        address_value_row.addWidget(self.address_value, 1)
        address_value_row.addWidget(self.copy_address_button)
        grid.addWidget(address_label, len(INFO_FIELDS), 0)
        grid.addLayout(address_value_row, len(INFO_FIELDS), 1)
        layout.addLayout(grid)
        self.show_address(None)

        text = self._messages.text
        self.open_folder_button = button(text("dashboard.open_folder"), "secondary", "folder", "openFolderButton")
        self.open_folder_button.clicked.connect(self._on_open_folder)
        self.open_logs_button = button(text("dashboard.open_logs"), "secondary", "external")
        self.open_logs_button.clicked.connect(self._on_open_logs)
        self.edit_button = button(text("dashboard.edit"), "ghost", "sliders")
        self.edit_button.clicked.connect(self.edit_requested)
        self.delete_button = button(text("dashboard.delete"), "ghost", "trash")
        self.delete_button.clicked.connect(self.delete_requested)
        # Side by side when both labels fit the inspector, otherwise one below the other (longer languages, scaling).
        self.button_rows = [
            WrapRow(first, second, 8, fill=True)
            for first, second in (
                (self.open_folder_button, self.open_logs_button),
                (self.edit_button, self.delete_button),
            )
        ]
        for button_row in self.button_rows:
            layout.addWidget(button_row)
        note = QLabel(text("server_details.next_launch_note"))
        note.setObjectName("controlHint")
        note.setWordWrap(True)
        layout.addWidget(note)
        return frame

    # --- tabs and side data -----------------------------------------------------------------

    def add_tab(self, key: str, widget: QWidget) -> None:
        """Add a main-column tab titled ``tabs.<key>``."""
        self._tab_keys.append(key)
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 14, 0, 0)
        page_layout.addWidget(widget)
        self.tabs.addTab(page, self._messages.text(f"tabs.{key}"))

    def show_tab(self, key: str) -> None:
        """Switch to the tab ``key`` if it exists."""
        if key in self._tab_keys:
            self.tabs.setCurrentIndex(self._tab_keys.index(key))

    @property
    def tab_keys(self) -> tuple[str, ...]:
        """Return the tab keys in display order."""
        return tuple(self._tab_keys)

    @property
    def current_tab(self) -> str:
        """Return the key of the shown tab."""
        return self._tab_keys[self.tabs.currentIndex()]

    def set_metrics_available(self, available: bool) -> None:
        """Show the resources card (only when metrics can be read at all)."""
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
            self.players_label.hide()
            return
        maximum = snapshot.max_players
        players.setText(
            self._messages.text("metrics.players_value", count=snapshot.player_count, maximum=maximum)
            if maximum is not None
            else str(snapshot.player_count)
        )
        names = self._messages.text("metrics.players_names", names=", ".join(snapshot.players))
        players.setToolTip(names)
        self.players_label.setText(names)
        self.players_label.setVisible(bool(snapshot.players))
        tps.setText(
            self._messages.text("metrics.tps_value", tps=f"{snapshot.tps:.1f}") if snapshot.tps is not None else idle
        )

    def show_metrics(self, snapshot: ServerMetricsSnapshot | None) -> None:
        """Show CPU, memory and uptime of the selected server, or dashes when it does not run."""
        text = self._messages.text
        if snapshot is None:
            self.live_label.setText(text("metrics.not_running"))
            for name in ("cpu", "memory", "uptime"):
                self.metric_values[name].setText(text("metrics.idle"))
                self.metric_rows[name].set_fraction(None)
            return
        self.live_label.setText(text("metrics.live"))
        self.metric_values["cpu"].setText(text("metrics.cpu_value", percent=f"{snapshot.cpu_percent:.0f}"))
        self.metric_rows["cpu"].set_fraction(snapshot.cpu_percent / 100)
        self.metric_values["memory"].setText(
            text("metrics.memory_value", used=f"{snapshot.memory_mb:.0f}", allocated=snapshot.allocated_mb)
        )
        self.metric_rows["memory"].set_fraction(snapshot.memory_mb / (snapshot.allocated_mb or 1))
        hours, rest = divmod(max(0, snapshot.uptime_seconds), 3600)
        minutes, seconds = divmod(rest, 60)
        self.metric_values["uptime"].setText(
            text("metrics.uptime_value", hours=hours, minutes=minutes, seconds=seconds)
        )

    def show_history(self, points: Sequence[MetricPoint], *, live: bool) -> None:
        """Draw the CPU and memory history of the selected server (dimmed once it stopped)."""
        text = self._messages.text
        minutes = HISTORY_CAPACITY * METRICS_SAMPLE_SECONDS // 60
        cpu = [point.cpu_percent for point in points]
        memory = [point.memory_mb for point in points]
        allocated = max((point.allocated_mb for point in points), default=0)
        if len(points) < 2:
            empty = text("metrics.history_empty")
            self.charts["cpu"].set_series((), 100, active=live, description=empty)
            self.charts["memory"].set_series((), 1, active=live, description=empty)
            return
        self.charts["cpu"].set_series(
            cpu,
            max(100.0, *cpu),
            active=live,
            description=text("metrics.history_cpu", minutes=minutes, low=f"{min(cpu):.0f}", high=f"{max(cpu):.0f}"),
        )
        self.charts["memory"].set_series(
            memory,
            float(allocated or max(memory)),
            active=live,
            description=text(
                "metrics.history_memory",
                minutes=minutes,
                low=f"{min(memory):.0f}",
                high=f"{max(memory):.0f}",
                allocated=allocated,
            ),
        )

    # --- rendering ------------------------------------------------------------------------

    def show_details_error(self, key: str | None, *, has_servers: bool = True) -> None:
        """Show a details error on the welcome page; without servers, explain how to get one."""
        default = "welcome.text" if has_servers else "welcome.first"
        self.welcome_text.setText(self._messages.text(key or default))

    def show_state(self, state: DashboardState) -> None:
        """Render the selected server, or the welcome page when nothing is selected."""
        row = state.row
        if row is None:
            self.pages.setCurrentWidget(self.welcome_page)
            return
        text = self._messages.text
        self.welcome_text.setText(text("welcome.text"))
        configuration = row.configuration
        memory = text("server_details.memory_value", memory_mb=configuration.memory_mb)
        self._folder = self._servers_root / configuration.directory
        self.title_label.setText(configuration.name)
        self.title_label.setToolTip(configuration.server_id)
        # Deleting is only possible while this server is not active (M2-GUI-04).
        self.delete_button.setEnabled(state.status in (ServerStatus.STOPPED, ServerStatus.UNKNOWN))
        self.subtitle_label.setText(
            text(
                "dashboard.subtitle_folder",
                jar_file=configuration.jar_file,
                memory=memory,
                folder=configuration.directory,
            )
        )
        self._set_info("directory", configuration.directory)
        self._set_info("location", str(self._folder), elide=True)
        self._set_info("jar_file", configuration.jar_file)
        self._set_info("memory", memory)

        self.status_pill.setText(text("dashboard.status_pill", status=text(STATUS_KEYS[state.status])))
        self.status_pill.setProperty("status", state.status.value)
        repolish(self.status_pill)

        self.start_button.setEnabled(state.can_start)
        self.stop_button.setEnabled(state.can_stop)
        self.kill_button.setVisible(state.can_kill or state.operation is Operation.KILLING)
        self.kill_button.setEnabled(state.can_kill)
        starting = state.operation is Operation.STARTING or state.status is ServerStatus.STARTING
        stopping = state.operation is Operation.STOPPING
        killing = state.operation is Operation.KILLING
        restarting = state.operation is Operation.RESTARTING
        self.restart_button.setEnabled(state.can_restart)
        self.restart_button.setText(text("dashboard.restarting" if restarting else "dashboard.restart"))
        self.start_button.setText(text("dashboard.starting" if starting else "dashboard.start"))
        if stopping:
            stop_key = "dashboard.stopping"
        elif state.stop_timed_out:
            stop_key = "dashboard.wait_again"
        else:
            stop_key = "dashboard.stop"
        self.stop_button.setText(text(stop_key))
        self.kill_button.setText(text("dashboard.killing" if killing else "dashboard.kill"))
        self.console.set_input_enabled(state.can_send_command)
        self._show_hint(state)
        if state.error is not None:
            self._show_banner(state.error, "error")
        elif state.notice is not None:
            self._show_banner(state.notice, "notice")
        else:
            self._show_banner(state.success, "success")
        self.pages.setCurrentWidget(self.dashboard_page)

    def _set_info(self, field: str, value: str, *, elide: bool = False) -> None:
        label = self.info_values[field]
        label.setToolTip(value)
        if elide:  # a full path is shortened in the middle; the tooltip keeps it whole
            value = label.fontMetrics().elidedText(value, Qt.TextElideMode.ElideMiddle, _INFO_VALUE_WIDTH)
        label.setText(value)

    def _show_hint(self, state: DashboardState) -> None:
        hint, warning = self._hint(state)
        self.hint_label.setText(hint)
        self.hint_label.setProperty("tone", "warning" if warning else "")
        repolish(self.hint_label)
        color = theme.WARNING_TEXT if warning else theme.TEXT_MUTED
        self.hint_icon.setPixmap(icons.pixmap("alert" if warning else "info", color, 14))
        self.hint_row.setVisible(bool(hint))

    def _hint(self, state: DashboardState) -> tuple[str, bool]:
        text = self._messages.text
        if state.hint is not None:
            return render_message(self._messages, state.hint), True
        if not state.java_available:
            return text("dashboard.hint.java_missing"), True
        if state.other_active_server is not None:
            return text("dashboard.hint.other_running", server_id=state.other_active_server), False
        if state.stop_timed_out and state.row is not None:
            return text("dashboard.hint.stop_timed_out", server_id=state.row.server_id), True
        if state.status is ServerStatus.STARTING:
            return text("dashboard.hint.starting"), False
        if state.status is ServerStatus.STOPPING:
            return text("dashboard.hint.stopping"), False
        if state.status is ServerStatus.RUNNING and state.operation is None:
            return text("dashboard.hint.running"), False
        return "", False

    def _show_banner(self, message: UserMessage | None, tone: str) -> None:
        self._banner_message = message
        if message is None:
            self.banner_row.clear()
            return
        self.banner_row.show_message(render_message(self._messages, message), tone, bool(message.details))
        self.banner.setToolTip(message.details)
        self.banner.setProperty("tone", tone)

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
