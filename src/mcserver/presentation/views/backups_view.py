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
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mcserver.application.backup_schedule import INTERVAL_HOURS_RANGE, KEEP_RANGE, BackupSchedule
from mcserver.application.backups import BackupInfo
from mcserver.presentation.controllers.backups import BackupsState
from mcserver.presentation.errors import render_message
from mcserver.presentation.i18n import Messages

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

    def __init__(self, messages: Messages) -> None:
        """Build the empty view."""
        super().__init__()
        self.setProperty("card", True)
        self._messages = messages
        self._backups: tuple[BackupInfo, ...] = ()
        self._state = BackupsState()
        title = QLabel(messages.text("backups.title"))
        title.setObjectName("consoleTitle")
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText(messages.text("backups.note.placeholder"))
        self.note_edit.setMaxLength(200)
        self.note_edit.returnPressed.connect(self._on_create)
        self.create_button = QPushButton(messages.text("backups.create"))
        self.create_button.setObjectName("primaryButton")
        self.create_button.clicked.connect(self._on_create)
        header = QHBoxLayout()
        header.addWidget(title)
        header.addWidget(self.note_edit, 1)
        header.addWidget(self.create_button)

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
        self.schedule_check.toggled.connect(self._on_schedule_edited)
        self.interval_spin.valueChanged.connect(self._on_schedule_edited)
        self.keep_spin.valueChanged.connect(self._on_schedule_edited)
        schedule_row = QHBoxLayout()
        schedule_row.setSpacing(8)
        schedule_row.addWidget(self.schedule_check)
        schedule_row.addStretch(1)
        schedule_row.addWidget(every)
        schedule_row.addWidget(self.interval_spin)
        schedule_row.addSpacing(8)
        schedule_row.addWidget(keep)
        schedule_row.addWidget(self.keep_spin)
        self.schedule_host = QFrame()
        self.schedule_host.setLayout(schedule_row)
        schedule_row.setContentsMargins(0, 0, 0, 0)
        self.schedule_hint = QLabel(messages.text("backups.schedule.hint"))
        self.schedule_hint.setObjectName("controlHint")
        self.schedule_hint.setWordWrap(True)
        self.message = QLabel()
        self.message.setObjectName("banner")
        self.message.setWordWrap(True)
        self.message.hide()
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(6)
        self.progress.hide()

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([messages.text(f"backups.column.{name}") for name in COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        header_view = self.table.horizontalHeader()
        for column in range(len(COLUMNS) - 1):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.empty_label = QLabel(messages.text("backups.empty"))
        self.empty_label.setObjectName("controlHint")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.restore_hint = QLabel(messages.text("backups.restore_running"))
        self.restore_hint.setObjectName("controlHint")
        self.restore_button = QPushButton(messages.text("backups.restore"))
        self.restore_button.setObjectName("secondaryButton")
        self.restore_button.clicked.connect(self._on_restore)
        self.delete_button = QPushButton(messages.text("backups.delete"))
        self.delete_button.setObjectName("secondaryButton")
        self.delete_button.clicked.connect(self._on_delete)
        actions = QHBoxLayout()
        actions.addWidget(self.restore_hint)
        actions.addStretch(1)
        actions.addWidget(self.restore_button)
        actions.addWidget(self.delete_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.schedule_host)
        layout.addWidget(self.schedule_hint)
        layout.addWidget(self.progress)
        layout.addWidget(self.message)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty_label, 1)
        layout.addLayout(actions)
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
        self.progress.setVisible(state.busy)
        if state.busy:
            self.progress.setRange(0, 0)  # busy indicator until the first progress report
        if state.message is None:
            self.message.hide()
        else:
            self.message.setText(render_message(self._messages, state.message))
            self.message.setProperty("tone", state.tone)
            style = self.message.style()
            style.unpolish(self.message)
            style.polish(self.message)
            self.message.show()
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

    def show_progress(self, done: int, total: int) -> None:
        """Show the progress of the running operation."""
        if total <= 0:
            return
        # QProgressBar holds ints; scale bytes to permille.
        self.progress.setRange(0, 1000)
        self.progress.setValue(min(1000, done * 1000 // total))

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
