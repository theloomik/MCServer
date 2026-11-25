"""Backups of the selected server: list, create, restore, delete (M3-GUI-04)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mcserver.application.backup_schedule import INTERVAL_HOURS_RANGE, KEEP_RANGE, BackupSchedule
from mcserver.application.backups import BackupInfo
from mcserver.presentation.controllers.backups import BackupsState
from mcserver.presentation.errors import render_message
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.progress_panel import ProgressPanel
from mcserver.presentation.views.widgets import Banner, WrapRow, button, icon_label, panel_bar

COLUMNS = ("date", "kind", "size", "note")


def format_created_at(value: str) -> str:
    """Show an ISO timestamp in local time, ``YYYY-MM-DD HH:MM``; unknown formats are shown as they are."""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is not None:
        moment = moment.astimezone()
    return moment.strftime("%Y-%m-%d %H:%M")


class BackupsView(QFrame):
    """Render ``BackupsState``; emits intents, asks no questions itself."""

    create_requested = Signal(str)  # note
    restore_requested = Signal(object)  # BackupInfo
    delete_requested = Signal(object)  # BackupInfo
    schedule_changed = Signal(object)  # BackupSchedule
    cancel_requested = Signal()

    def __init__(self, messages: Messages) -> None:
        """Build the empty view."""
        super().__init__()
        self.setProperty("card", True)
        self._messages = messages
        self._backups: tuple[BackupInfo, ...] = ()
        self._state = BackupsState()
        toolbar, bar = panel_bar("top")
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText(messages.text("backups.note.placeholder"))
        self.note_edit.setMaxLength(200)
        self.note_edit.setAccessibleName(messages.text("backups.note.placeholder"))
        self.note_edit.returnPressed.connect(self._on_create)
        self.create_button = button(messages.text("backups.create"), "primary", "archive")
        self.create_button.clicked.connect(self._on_create)
        bar.addWidget(icon_label("archive"))
        bar.addWidget(self.note_edit, 1)
        bar.addWidget(self.create_button)

        self._filling = False
        self.schedule_check = QCheckBox(messages.text("backups.schedule.enabled"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(*INTERVAL_HOURS_RANGE)
        self.interval_spin.setSuffix(messages.text("backups.schedule.hours_suffix"))
        self.keep_spin = QSpinBox()
        self.keep_spin.setRange(*KEEP_RANGE)
        for spin in (self.interval_spin, self.keep_spin):
            spin.setFixedWidth(84)
        every = QLabel(messages.text("backups.schedule.every"))
        every.setObjectName("fieldLabel")
        keep = QLabel(messages.text("backups.schedule.keep"))
        keep.setObjectName("fieldLabel")
        every.setBuddy(self.interval_spin)
        keep.setBuddy(self.keep_spin)
        self.schedule_check.toggled.connect(self._on_schedule_edited)
        self.interval_spin.valueChanged.connect(self._on_schedule_edited)
        self.keep_spin.valueChanged.connect(self._on_schedule_edited)
        self.schedule_host, schedule_row = panel_bar("band")
        schedule_row.setContentsMargins(16, 8, 12, 8)
        switch = QWidget()
        switch_row = QHBoxLayout(switch)
        switch_row.setContentsMargins(0, 0, 0, 0)
        switch_row.addWidget(icon_label("clock"))
        switch_row.addWidget(self.schedule_check)
        values = QWidget()
        values_row = QHBoxLayout(values)
        values_row.setContentsMargins(0, 0, 0, 0)
        values_row.addWidget(every)
        values_row.addWidget(self.interval_spin)
        values_row.addSpacing(8)
        values_row.addWidget(keep)
        values_row.addWidget(self.keep_spin)
        self.schedule_row = WrapRow(switch, values)
        schedule_row.addWidget(self.schedule_row)
        self.schedule_hint = QLabel(messages.text("backups.schedule.hint"))
        self.schedule_hint.setObjectName("controlHint")
        self.schedule_hint.setWordWrap(True)

        self.message_banner = Banner()
        self.message = self.message_banner.text
        self.progress = ProgressPanel(messages)
        self.progress.cancel_requested.connect(self.cancel_requested)
        notices = QVBoxLayout()
        notices.setContentsMargins(16, 10, 16, 6)
        notices.setSpacing(8)
        notices.addWidget(self.schedule_hint)
        notices.addWidget(self.progress)
        notices.addWidget(self.message_banner)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setAccessibleName(messages.text("a11y.backups_table"))
        self.table.setHorizontalHeaderLabels([messages.text(f"backups.column.{name}").upper() for name in COLUMNS])
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
        self.empty_label = QLabel(messages.text("backups.empty"))
        self.empty_label.setObjectName("emptyText")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        footer, actions = panel_bar("bottom")
        actions.setContentsMargins(16, 10, 12, 10)
        self.restore_hint = QLabel(messages.text("backups.restore_running"))
        self.restore_hint.setObjectName("controlHint")
        self.restore_button = button(messages.text("backups.restore"), "secondary", "restart")
        self.restore_button.clicked.connect(self._on_restore)
        self.delete_button = button(messages.text("backups.delete"), "danger", "trash")
        self.delete_button.clicked.connect(self._on_delete)
        actions.addWidget(self.restore_hint)
        actions.addStretch(1)
        actions.addWidget(self.restore_button)
        actions.addWidget(self.delete_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(self.schedule_host)
        layout.addLayout(notices)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty_label, 1)
        layout.addWidget(footer)
        self.show_state(self._state)

    def selected_backup(self) -> BackupInfo | None:
        """Return the selected backup, if any."""
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        return self._backups[index] if 0 <= index < len(self._backups) else None

    def show_state(self, state: BackupsState) -> None:
        """Render ``state``; keeps the selection when the same backup is still listed."""
        previous = self.selected_backup()
        self._state = state
        if state.backups != self._backups:
            self._fill(state.backups, previous.backup_id if previous else None)
        has_backups = bool(state.backups)
        self.table.setVisible(has_backups)
        self.empty_label.setVisible(not has_backups)
        if state.busy:
            self.progress.start(cancellable=state.cancellable)
            if state.cancelling:
                self.progress.show_cancelling()
        else:
            self.progress.finish()
        if state.message is None:
            self.message_banner.clear()
        else:
            self.message_banner.show_message(render_message(self._messages, state.message), state.tone)
        self.restore_hint.setVisible(state.server_active)
        self._show_schedule(state.schedule)
        self.note_edit.setEnabled(state.can_create)
        self.create_button.setEnabled(state.can_create)
        self._update_buttons()

    def _show_schedule(self, schedule: BackupSchedule | None) -> None:
        visible = schedule is not None
        self.schedule_host.setVisible(visible)
        self.schedule_hint.setVisible(visible)
        if schedule is None:
            return
        self._filling = True
        try:
            self.schedule_check.setChecked(schedule.enabled)
            self.interval_spin.setValue(schedule.interval_hours)
            self.keep_spin.setValue(schedule.keep)
        finally:
            self._filling = False
        self.interval_spin.setEnabled(schedule.enabled)
        self.keep_spin.setEnabled(schedule.enabled)

    def _on_schedule_edited(self) -> None:
        if self._filling:
            return
        self.schedule_changed.emit(
            BackupSchedule(self.schedule_check.isChecked(), self.interval_spin.value(), self.keep_spin.value())
        )

    def show_progress(self, progress: object) -> None:
        """Show one ``Progress`` report of the running operation."""
        self.progress.show_progress(progress)

    def _fill(self, backups: tuple[BackupInfo, ...], selected_id: str | None) -> None:
        self._backups = backups
        self.table.setRowCount(len(backups))
        for row, backup in enumerate(backups):
            kind = self._messages.text(f"backups.kind.{backup.kind.value}")
            if backup.online:
                kind = self._messages.text("backups.kind.online", kind=kind)
            cells = (
                format_created_at(backup.created_at),
                kind,
                self._size(backup.size_bytes),
                backup.note,
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(backup.backup_id)
                self.table.setItem(row, column, item)
            if backup.backup_id == selected_id:
                self.table.selectRow(row)

    def _size(self, size_bytes: int) -> str:
        if size_bytes < 1024 * 1024:
            return self._messages.text("backups.size_kb", kilobytes=max(1, round(size_bytes / 1024)))
        return self._messages.text("backups.size_value", megabytes=f"{size_bytes / (1024 * 1024):.1f}")

    def _update_buttons(self) -> None:
        selected = self.selected_backup() is not None
        self.restore_button.setEnabled(selected and self._state.can_restore)
        self.delete_button.setEnabled(selected and not self._state.busy)

    def _on_create(self) -> None:
        if self._state.can_create:
            self.create_requested.emit(self.note_edit.text())
            self.note_edit.clear()

    def _on_restore(self) -> None:
        backup = self.selected_backup()
        if backup is not None and self._state.can_restore:
            self.restore_requested.emit(backup)

    def _on_delete(self) -> None:
        backup = self.selected_backup()
        if backup is not None and not self._state.busy:
            self.delete_requested.emit(backup)
