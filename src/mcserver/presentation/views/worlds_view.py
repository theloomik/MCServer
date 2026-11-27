"""Worlds of the selected server (M3-GUI-07)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mcserver.application.worlds import WorldInfo
from mcserver.presentation.controllers.worlds import WorldsState
from mcserver.presentation.errors import render_message
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.progress_panel import ProgressPanel
from mcserver.presentation.views.widgets import Banner, button, icon_label, panel_bar

COLUMNS = ("name", "size", "modified", "dimensions")


class WorldsView(QFrame):
    """Render ``WorldsState``; emits intents and asks no questions itself."""

    use_requested = Signal(str)
    new_requested = Signal()
    import_folder_requested = Signal()
    import_zip_requested = Signal()
    export_requested = Signal(str)
    delete_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, messages: Messages) -> None:
        """Build the empty view."""
        super().__init__()
        self.setProperty("card", True)
        self._messages = messages
        self._worlds: tuple[WorldInfo, ...] = ()
        self._state = WorldsState()
        toolbar, bar = panel_bar("top")
        self.current_label = QLabel()
        self.current_label.setObjectName("controlHint")
        self.new_button = button(messages.text("worlds.new"), "secondary", "plus")
        self.new_button.clicked.connect(self.new_requested)
        self.import_folder_button = button(messages.text("worlds.import_folder"), "secondary", "folder")
        self.import_folder_button.clicked.connect(self.import_folder_requested)
        self.import_zip_button = button(messages.text("worlds.import_zip"), "secondary", "import")
        self.import_zip_button.clicked.connect(self.import_zip_requested)
        bar.addWidget(icon_label("world"))
        bar.addWidget(self.current_label, 1)
        bar.addWidget(self.new_button)
        bar.addWidget(self.import_folder_button)
        bar.addWidget(self.import_zip_button)

        self.message_banner = Banner()
        self.message = self.message_banner.text
        self.progress = ProgressPanel(messages)
        self.progress.cancel_requested.connect(self.cancel_requested)
        self.loading_bar = QProgressBar()
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedHeight(4)
        self.loading_bar.setRange(0, 0)
        self.loading_bar.hide()
        notices = QVBoxLayout()
        notices.setContentsMargins(16, 12, 16, 4)
        notices.setSpacing(8)
        notices.addWidget(self.message_banner)
        notices.addWidget(self.progress)
        notices.addWidget(self.loading_bar)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setAccessibleName(messages.text("a11y.worlds_table"))
        self.table.setHorizontalHeaderLabels([messages.text(f"worlds.column.{name}").upper() for name in COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.verticalHeader().setDefaultSectionSize(38)
        header_view = self.table.horizontalHeader()
        header_view.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for column in range(len(COLUMNS) - 1):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.empty_label = QLabel(messages.text("worlds.empty"))
        self.empty_label.setObjectName("emptyText")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        footer, actions = panel_bar("bottom")
        actions.setContentsMargins(16, 10, 12, 10)
        self.running_hint = QLabel(messages.text("worlds.stop_to_switch"))
        self.running_hint.setObjectName("controlHint")
        self.use_button = button(messages.text("worlds.use"), "primary", "check")
        self.use_button.clicked.connect(self._on_use)
        self.export_button = button(messages.text("worlds.export"), "secondary", "download")
        self.export_button.clicked.connect(self._on_export)
        self.delete_button = button(messages.text("worlds.delete"), "danger", "trash")
        self.delete_button.clicked.connect(self._on_delete)
        actions.addWidget(self.running_hint)
        actions.addStretch(1)
        actions.addWidget(self.use_button)
        actions.addWidget(self.export_button)
        actions.addWidget(self.delete_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addLayout(notices)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty_label, 1)
        layout.addWidget(footer)
        self.show_state(self._state)

    def selected_world(self) -> WorldInfo | None:
        """Return the selected world, if any."""
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        return self._worlds[index] if 0 <= index < len(self._worlds) else None

    def show_state(self, state: WorldsState) -> None:
        """Render ``state``; keeps the selection when the same world is still listed."""
        previous = self.selected_world()
        self._state = state
        if state.worlds != self._worlds:
            self._fill(state.worlds, previous.name if previous else None)
        self.table.setVisible(bool(state.worlds))
        self.empty_label.setVisible(not state.worlds and not state.loading)
        if state.level_name:
            key = "worlds.current" if state.level_exists else "worlds.current_new"
            self.current_label.setText(self._messages.text(key, name=state.level_name))
        self.current_label.setVisible(bool(state.level_name))
        if state.busy:
            self.progress.start(cancellable=state.cancellable)
            if state.cancelling:
                self.progress.show_cancelling()
        else:
            self.progress.finish()
        self.loading_bar.setVisible(state.loading and not state.busy)
        if state.message is None:
            self.message_banner.clear()
        else:
            self.message_banner.show_message(render_message(self._messages, state.message), state.tone)
        self.running_hint.setVisible(state.server_active)
        self.new_button.setEnabled(state.can_switch)
        for import_button in (self.import_folder_button, self.import_zip_button):
            import_button.setEnabled(state.can_change_files)
        self._update_buttons()

    def show_progress(self, progress: object) -> None:
        """Show one ``Progress`` report of the running operation."""
        self.progress.show_progress(progress)

    def _fill(self, worlds: tuple[WorldInfo, ...], selected: str | None) -> None:
        self._worlds = worlds
        self.table.setRowCount(len(worlds))
        for row, world in enumerate(worlds):
            name = self._messages.text("worlds.active_name", name=world.name) if world.active else world.name
            modified = datetime.fromtimestamp(world.modified_at).strftime("%Y-%m-%d %H:%M")
            folders = self._messages.text("worlds.folders", folders=", ".join(world.folders))
            for column, text in enumerate((name, self._size(world.size_bytes), modified, folders)):
                item = QTableWidgetItem(text)
                self.table.setItem(row, column, item)
            if world.name == selected:
                self.table.selectRow(row)

    def _size(self, size_bytes: int) -> str:
        if size_bytes < 1024 * 1024:
            return self._messages.text("backups.size_kb", kilobytes=max(1, round(size_bytes / 1024)))
        return self._messages.text("backups.size_value", megabytes=f"{size_bytes / (1024 * 1024):.1f}")

    def _update_buttons(self) -> None:
        world = self.selected_world()
        state = self._state
        self.use_button.setEnabled(world is not None and not world.active and state.can_switch)
        self.export_button.setEnabled(
            world is not None and state.can_change_files and not (world.active and state.server_active)
        )
        self.delete_button.setEnabled(world is not None and not world.active and state.can_change_files)

    def _on_use(self) -> None:
        world = self.selected_world()
        if world is not None:
            self.use_requested.emit(world.name)

    def _on_export(self) -> None:
        world = self.selected_world()
        if world is not None:
            self.export_requested.emit(world.name)

    def _on_delete(self) -> None:
        world = self.selected_world()
        if world is not None:
            self.delete_requested.emit(world.name)
