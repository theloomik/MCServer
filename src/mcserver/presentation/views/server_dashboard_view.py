"""Central dashboard (UX overhaul): header with status and actions; Overview = stat tiles + console."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
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
from mcserver.presentation.views.memory_slider import format_gb
from mcserver.presentation.views.server_console_view import ServerConsoleView
from mcserver.presentation.views.status_text import STATUS_KEYS
from mcserver.presentation.views.widgets import Banner, button, icon_button, repolish

METRIC_TILES = ("players", "memory", "cpu", "uptime")
"""The stat tiles, in order; each has the label key ``metrics.<name>``."""
_CHART_COLORS = {"cpu": "ACCENT", "memory": "INFO"}
"""Tiles with a history chart, and the theme colour of each."""
METRICS_SAMPLE_SECONDS = 2
"""How often the window samples metrics (``main_window.METRICS_INTERVAL_MS``)."""
TILE_COLUMNS_NARROW_BELOW = 620
"""Below this width the tiles form a 2 × 2 grid instead of one row."""
_NO_TOOLTIP = ""


class StatTile(QFrame):
    """One figure: a caption, a large value, a quiet line below and, for CPU and memory, a history chart."""

    def __init__(self, caption_text: str, idle: str, chart: Sparkline | None = None) -> None:
        super().__init__()
        self.setObjectName("statTile")
        self.caption = QLabel(caption_text.upper())
        self.caption.setObjectName("tileCaption")
        self.value = QLabel(idle)
        self.value.setObjectName("tileValue")
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = QLabel()
        self.detail.setObjectName("tileDetail")
        self.detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.chart = chart
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 8)
        layout.setSpacing(1)
        layout.addWidget(self.caption)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)
        layout.addSpacing(4)
        if chart is not None:
            chart.setFixedHeight(28)
            layout.addWidget(chart)
        else:
            layout.addSpacing(28)  # every tile has the same height, chart or not
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class TileGrid(QWidget):
    """Four tiles in a row, or two rows of two when the window is narrow."""

    def __init__(self, tiles: Sequence[StatTile]) -> None:
        super().__init__()
        self.tiles = list(tiles)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.columns = 0
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._arrange(len(self.tiles))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        """Need the width of two columns and the height of the rows shown now."""
        tile = max((tile.minimumSizeHint() for tile in self.tiles), key=lambda size: size.width())
        height = max(tile.sizeHint().height() for tile in self.tiles)
        rows = -(-len(self.tiles) // max(1, self.columns))
        return QSize(tile.width() * 2 + 12, height * rows + 12 * (rows - 1))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        """Rearrange when the width crosses the threshold."""
        columns = len(self.tiles) if event.size().width() >= TILE_COLUMNS_NARROW_BELOW else 2
        if columns != self.columns:
            self._arrange(columns)
        super().resizeEvent(event)

    def _arrange(self, columns: int) -> None:
        for tile in self.tiles:
            self.grid.removeWidget(tile)
        for index, tile in enumerate(self.tiles):
            self.grid.addWidget(tile, index // columns, index % columns)
        for column in range(len(self.tiles)):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        self.columns = columns
        self.updateGeometry()


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

        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        layout.addStretch(1)
        layout.addWidget(tile, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)
        layout.addWidget(self.welcome_text, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(4)
        layout.addLayout(actions)
        layout.addSpacing(6)
        layout.addStretch(1)
        return page

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 18, 28, 16)
        layout.setSpacing(10)
        layout.addLayout(self._build_header())
        self.hint_row = QWidget()
        hint_layout = QHBoxLayout(self.hint_row)
        hint_layout.setContentsMargins(0, 0, 0, 0)
        hint_layout.setSpacing(8)
        self.hint_icon = QLabel()
        self.hint_icon.setFixedSize(16, 16)
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
        self.tabs.setCornerWidget(self._build_server_actions(), Qt.Corner.TopRightCorner)
        self._tab_keys: list[str] = []
        self.overview = self._build_overview()
        self.add_tab("overview", self.overview)
        layout.addWidget(self.tabs, 1)
        return page

    def _build_header(self) -> QHBoxLayout:
        text = self._messages.text
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
        # Where players connect: the one network detail beginners need, with a copy button.
        address_caption = QLabel(text("dashboard.address"))
        address_caption.setObjectName("serverSubtitle")
        self.address_value = QLabel()
        self.address_value.setObjectName("addressValue")
        self.address_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.copy_address_button = icon_button("copy", text("dashboard.copy_address"))
        self.copy_address_button.clicked.connect(self._on_copy_address)
        # The summary may be cut off in a narrow window (its tooltip keeps it whole); it never widens the window.
        self.subtitle_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        address_row = QWidget()
        address = QHBoxLayout(address_row)
        address.setContentsMargins(0, 0, 0, 0)
        address.setSpacing(6)
        address.addWidget(address_caption)
        address.addWidget(self.address_value)
        address.addWidget(self.copy_address_button)
        address.addStretch(1)
        # Like the summary, the address line may be cut off in a narrow window rather than widen it.
        address_row.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        address_row.setMinimumHeight(self.copy_address_button.sizeHint().height())
        titles = QVBoxLayout()
        titles.setSpacing(3)
        titles.addLayout(title_row)
        titles.addWidget(self.subtitle_label)
        titles.addWidget(address_row)

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
        self.show_address(None)
        return header

    def _build_server_actions(self) -> QWidget:
        """Folder, logs, edit and delete: quiet icon buttons beside the tabs (labels in tooltips and for readers)."""
        text = self._messages.text
        self.open_folder_button = icon_button("folder", text("dashboard.open_folder"), "toolButton")
        self.open_folder_button.clicked.connect(self._on_open_folder)
        self.open_logs_button = icon_button("external", text("dashboard.open_logs"), "toolButton")
        self.open_logs_button.clicked.connect(self._on_open_logs)
        self.edit_button = icon_button("sliders", text("dashboard.edit"), "toolButton")
        self.edit_button.clicked.connect(self.edit_requested)
        self.delete_button = icon_button("trash", text("dashboard.delete"), "toolButton")
        self.delete_button.clicked.connect(self.delete_requested)
        actions = QWidget()
        actions.setObjectName("tabActions")
        row = QHBoxLayout(actions)
        row.setContentsMargins(0, 0, 0, 6)
        row.setSpacing(2)
        for widget in (self.open_folder_button, self.open_logs_button, self.edit_button, self.delete_button):
            row.addWidget(widget)
        return actions

    def _build_overview(self) -> QWidget:
        """Four stat tiles above the console; the console takes the rest of the height."""
        text = self._messages.text
        idle = text("metrics.idle")
        self.charts: dict[str, Sparkline] = {}
        self.tiles: dict[str, StatTile] = {}
        for name in METRIC_TILES:
            chart = None
            if name in _CHART_COLORS:
                chart = Sparkline(_CHART_COLORS[name], HISTORY_CAPACITY)
                chart.setAccessibleName(text(f"metrics.{name}"))
                self.charts[name] = chart
            self.tiles[name] = StatTile(text(f"metrics.{name}"), idle, chart)
        self.metric_values: dict[str, QLabel] = {name: tile.value for name, tile in self.tiles.items()}
        self.metric_values["tps"] = self.tiles["uptime"].detail
        self.players_label = self.tiles["players"].detail
        self.metrics_card = TileGrid(list(self.tiles.values()))
        overview = QWidget()
        layout = QVBoxLayout(overview)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self.metrics_card)
        layout.addWidget(self.console, 1)
        self.show_history((), live=False)
        self.show_activity(None)
        return overview

    # --- tabs and side data -----------------------------------------------------------------

    def add_tab(self, key: str, widget: QWidget) -> None:
        """Add a main-column tab titled ``tabs.<key>``."""
        self._tab_keys.append(key)
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 12, 0, 0)
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
        """Show the stat tiles (only when metrics can be read at all)."""
        self.metrics_card.setVisible(available)

    def show_address(self, address: ServerAddress | None) -> None:
        """Show where LAN players connect (``None`` when it is not known)."""
        self._address = address
        self.address_value.setText(str(address) if address else self._messages.text("dashboard.address_unknown"))
        self.address_value.setToolTip(self.address_value.text())
        self.copy_address_button.setVisible(address is not None)

    def show_activity(self, snapshot: ServerActivitySnapshot | None) -> None:
        """Show players online and tick rate of the running server, or dashes."""
        text = self._messages.text
        players, tps = self.metric_values["players"], self.metric_values["tps"]
        idle = text("metrics.idle")
        if snapshot is None:
            players.setText(idle)
            players.setToolTip(_NO_TOOLTIP)
            self.players_label.setText(text("metrics.players_none"))
            self.players_label.setToolTip(_NO_TOOLTIP)
            tps.setText(text("metrics.tps_line", tps=idle))
            return
        maximum = snapshot.max_players
        players.setText(
            text("metrics.players_value", count=snapshot.player_count, maximum=maximum)
            if maximum is not None
            else str(snapshot.player_count)
        )
        names = text("metrics.players_names", names=", ".join(snapshot.players))
        players.setToolTip(names if snapshot.players else _NO_TOOLTIP)
        self.players_label.setText(names if snapshot.players else text("metrics.players_none"))
        self.players_label.setToolTip(names if snapshot.players else _NO_TOOLTIP)
        tps.setText(text("metrics.tps_line", tps=f"{snapshot.tps:.1f}" if snapshot.tps is not None else idle))

    def show_metrics(self, snapshot: ServerMetricsSnapshot | None) -> None:
        """Show CPU, memory and uptime of the selected server, or dashes when it does not run."""
        text = self._messages.text
        tiles = self.tiles
        if snapshot is None:
            for name in ("cpu", "memory", "uptime"):
                self.metric_values[name].setText(text("metrics.idle"))
            tiles["cpu"].detail.setText(text("metrics.not_running"))
            tiles["memory"].detail.setText(text("metrics.not_running"))
            return
        self.metric_values["cpu"].setText(text("metrics.cpu_value", percent=f"{snapshot.cpu_percent:.0f}"))
        tiles["cpu"].detail.setText(text("metrics.cpu_detail"))
        self.metric_values["memory"].setText(text("metrics.memory_gb", used=format_gb(round(snapshot.memory_mb))))
        tiles["memory"].detail.setText(text("metrics.memory_of", allocated=format_gb(snapshot.allocated_mb)))
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
        memory = text("memory.gb", value=format_gb(configuration.memory_mb))
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
        self.subtitle_label.setToolTip(self.subtitle_label.text())
        folder_tip = self._messages.text("dashboard.open_folder_at", path=str(self._folder))
        self.open_folder_button.setToolTip(folder_tip)

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

    def _show_hint(self, state: DashboardState) -> None:
        hint, warning = self._hint(state)
        self.hint_label.setText(hint)
        self.hint_label.setProperty("tone", "warning" if warning else "")
        repolish(self.hint_label)
        color = theme.WARNING_TEXT if warning else theme.TEXT_MUTED
        self.hint_icon.setPixmap(icons.pixmap("alert" if warning else "info", color, 16))
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
        if state.status is ServerStatus.STOPPED and state.operation is None:
            return text("dashboard.hint.stopped"), False
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
