"""Editor for ``server.properties`` (M4 design): toolbar, two-column typed editors, unsaved-changes count."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mcserver.domain.server_properties import KNOWN_PROPERTIES, PropertyKind
from mcserver.presentation import icons, theme
from mcserver.presentation.controllers.properties import PropertiesState
from mcserver.presentation.errors import render_message
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.widgets import Banner, button, caption, icon_label, panel_bar, repolish

Editor = QCheckBox | QComboBox | QSpinBox | QLineEdit
COLUMNS = 2
_KEY_WIDTH = 180


class ServerPropertiesView(QFrame):
    """Show one editor per property; emits the changed values on Save, never writes files itself."""

    save_requested = Signal(object)  # dict[str, str]
    reload_requested = Signal()

    def __init__(self, messages: Messages) -> None:
        """Build the empty editor."""
        super().__init__()
        self.setProperty("card", True)
        self._messages = messages
        self._editors: dict[str, Editor] = {}
        self._initial: dict[str, str] = {}
        self._rows: dict[str, tuple[QLabel, QWidget, QLabel]] = {}
        self._cells: dict[str, QWidget] = {}
        self._present: set[str] = set()
        self._server_id: str | None = None

        toolbar, bar = panel_bar("top")
        title = QLabel(messages.text("properties.title"))
        title.setObjectName("monoTitle")
        self.unsaved_label = QLabel()
        self.unsaved_label.setObjectName("unsavedCount")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(messages.text("properties.search"))
        self.filter_edit.setFixedWidth(220)
        self.filter_edit.addAction(icons.icon("search", theme.TEXT_FAINT), QLineEdit.ActionPosition.LeadingPosition)
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.reload_button = button(messages.text("properties.reload"), "ghost", "restart")
        self.reload_button.clicked.connect(self.reload_requested)
        self.save_button = button(messages.text("properties.save"), "primary", "save")
        self.save_button.clicked.connect(self._on_save)
        bar.addWidget(icon_label("sliders"))
        bar.addWidget(title)
        bar.addWidget(self.unsaved_label, 1)
        bar.addWidget(self.filter_edit)
        bar.addWidget(self.reload_button)
        bar.addWidget(self.save_button)

        self.message_banner = Banner()
        self.message = self.message_banner.text
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(20, 16, 20, 16)
        self.content_layout.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.content)
        banner_box = QVBoxLayout()
        banner_box.setContentsMargins(20, 14, 20, 0)
        banner_box.addWidget(self.message_banner)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addLayout(banner_box)
        layout.addWidget(scroll, 1)
        self._update_changes()

    @property
    def editors(self) -> dict[str, Editor]:
        """Return the editor of each shown key."""
        return self._editors

    def show_state(self, state: PropertiesState) -> None:
        """Rebuild the editors for ``state`` (keeps the filter, and the user's edits when a save was refused)."""
        pending = self.changed_values() if state.problems and state.server_id == self._server_id else {}
        self._server_id = state.server_id
        self._rebuild(state)
        for key, value in pending.items():
            if key in self._editors:
                self._set_value(self._editors[key], value)
        message = state.message
        if message is None and not state.exists:
            self._show_message(self._messages.text("properties.missing"), "notice")
        elif message is not None:
            self._show_message(render_message(self._messages, message), state.tone)
        else:
            self.message_banner.clear()
        self.reload_button.setEnabled(state.server_id is not None)
        self._update_changes()

    def values(self) -> dict[str, str]:
        """Return what the editors contain, as property strings."""
        result: dict[str, str] = {}
        for key, editor in self._editors.items():
            if isinstance(editor, QCheckBox):
                result[key] = "true" if editor.isChecked() else "false"
            elif isinstance(editor, QComboBox):
                result[key] = editor.currentText()
            elif isinstance(editor, QSpinBox):
                result[key] = str(editor.value())
            else:
                result[key] = editor.text()
        return result

    def changed_values(self) -> dict[str, str]:
        """Return only the values the user changed since the editors were filled."""
        return {key: value for key, value in self.values().items() if self._initial.get(key) != value}

    # --- building ---------------------------------------------------------------------------

    def _clear(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._editors.clear()
        self._rows.clear()
        self._cells.clear()

    def _rebuild(self, state: PropertiesState) -> None:
        self._clear()
        values = dict(state.values)
        self._present = set(values)
        known = [key for key in KNOWN_PROPERTIES if key in values or not state.exists]
        others = [key for key in values if key not in KNOWN_PROPERTIES]
        for caption_key, keys in (("properties.known", known), ("properties.other", others)):
            if not keys:
                continue
            self.content_layout.addWidget(caption(self._messages.text(caption_key)))
            section = QWidget()
            grid = QGridLayout(section)
            grid.setContentsMargins(0, 0, 0, 6)
            grid.setHorizontalSpacing(28)
            grid.setVerticalSpacing(10)
            for index, key in enumerate(keys):
                cell = self._cell(key, values.get(key, ""), state.problems.get(key))
                grid.addWidget(cell, index // COLUMNS, index % COLUMNS)
            for column in range(COLUMNS):
                grid.setColumnStretch(column, 1)
            self.content_layout.addWidget(section)
        self.content_layout.addStretch(1)
        self._initial = self.values()
        self._apply_filter(self.filter_edit.text())

    def _cell(self, key: str, value: str, problem: str | None) -> QWidget:
        cell = QWidget()
        label = QLabel(key)
        label.setObjectName("propertyKey")
        label.setFixedWidth(_KEY_WIDTH)
        label.setProperty("invalid", bool(problem))
        editor = self._editor(key, value, present=key in self._present)
        editor.setProperty("invalid", bool(problem))
        self._watch(editor)
        error = QLabel(self._messages.text("properties.invalid_value", name=key, reason=problem) if problem else "")
        error.setObjectName("fieldError")
        error.setWordWrap(True)
        error.setVisible(bool(problem))
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(12)
        line.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
        line.addWidget(editor, 1)
        error_line = QHBoxLayout()
        error_line.setContentsMargins(_KEY_WIDTH + 12, 0, 0, 0)
        error_line.addWidget(error)
        box = QVBoxLayout(cell)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        box.addLayout(line)
        box.addLayout(error_line)
        self._editors[key] = editor
        self._rows[key] = (label, editor, error)
        self._cells[key] = cell
        return cell

    def _editor(self, key: str, value: str, *, present: bool) -> Editor:
        if not present:
            # Not in the file (yet): the server uses its own default, which MCServer does not guess.
            blank = QLineEdit()
            blank.setPlaceholderText(self._messages.text("properties.default"))
            return blank
        spec = KNOWN_PROPERTIES.get(key)
        if spec is not None and spec.kind is PropertyKind.BOOLEAN and value.strip().lower() in ("true", "false", ""):
            check = QCheckBox()
            check.setChecked(value.strip().lower() == "true")
            return check
        if spec is not None and spec.kind is PropertyKind.CHOICE and value.strip().lower() in (*spec.choices, ""):
            combo = QComboBox()
            combo.addItems(spec.choices)
            combo.setCurrentText(value.strip().lower() or spec.choices[0])
            return combo
        if spec is not None and spec.kind in (PropertyKind.INTEGER, PropertyKind.PORT):
            try:
                number = int(value.strip() or "0")
            except ValueError:
                number = None
            low, high = spec.minimum or 0, spec.maximum or 2147483647
            if number is not None and low <= number <= high:
                spin = QSpinBox()
                spin.setRange(low, high)
                spin.setValue(number)
                return spin
        # Unknown keys, and known keys holding a value the typed editor cannot show, stay plain text.
        return QLineEdit(value)

    def _watch(self, editor: Editor) -> None:
        if isinstance(editor, QCheckBox):
            editor.toggled.connect(self._update_changes)
        elif isinstance(editor, QComboBox):
            editor.currentTextChanged.connect(self._update_changes)
        elif isinstance(editor, QSpinBox):
            editor.valueChanged.connect(self._update_changes)
        else:
            editor.textChanged.connect(self._update_changes)

    @staticmethod
    def _set_value(editor: Editor, value: str) -> None:
        if isinstance(editor, QCheckBox):
            editor.setChecked(value.strip().lower() == "true")
        elif isinstance(editor, QComboBox):
            editor.setCurrentText(value)
        elif isinstance(editor, QSpinBox):
            try:
                editor.setValue(int(value))
            except ValueError:
                return
        else:
            editor.setText(value)

    # --- state ------------------------------------------------------------------------------

    def _update_changes(self, *_args: object) -> None:
        count = len(self.changed_values())
        self.unsaved_label.setText(self._messages.plural("properties.unsaved", count) if count else "")
        self.save_button.setEnabled(self._server_id is not None and count > 0)

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for key, cell in self._cells.items():
            cell.setVisible(not needle or needle in key.lower())

    def _show_message(self, text: str, tone: str) -> None:
        self.message_banner.show_message(text, tone)
        repolish(self.message)

    def _on_save(self) -> None:
        self.save_requested.emit(self.changed_values())
