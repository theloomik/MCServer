"""Editor for ``server.properties``: typed fields for known keys, text for the rest (M3-GUI-02)."""

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
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mcserver.domain.server_properties import KNOWN_PROPERTIES, PropertyKind
from mcserver.presentation.controllers.properties import PropertiesState
from mcserver.presentation.errors import render_message
from mcserver.presentation.i18n import Messages

Editor = QCheckBox | QComboBox | QSpinBox | QLineEdit


class ServerPropertiesView(QFrame):
    """Show one editor per property; emits the values on Save, never writes files itself."""

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
        self._present: set[str] = set()
        title = QLabel(messages.text("properties.title"))
        title.setObjectName("consoleTitle")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(messages.text("properties.search"))
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.reload_button = QPushButton(messages.text("properties.reload"))
        self.reload_button.setObjectName("secondaryButton")
        self.reload_button.clicked.connect(self.reload_requested)
        self.save_button = QPushButton(messages.text("properties.save"))
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._on_save)
        header = QHBoxLayout()
        header.addWidget(title)
        header.addWidget(self.filter_edit, 1)
        header.addWidget(self.reload_button)
        header.addWidget(self.save_button)
        self.message = QLabel()
        self.message.setObjectName("banner")
        self.message.setWordWrap(True)
        self.message.hide()
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.grid_host)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.message)
        layout.addWidget(scroll, 1)

    @property
    def editors(self) -> dict[str, Editor]:
        """Return the editor of each shown key."""
        return self._editors

    def show_state(self, state: PropertiesState) -> None:
        """Rebuild the editors for ``state`` (keeps the filter)."""
        self._rebuild(state)
        message = state.message
        if message is None and not state.exists:
            self._show_message(self._messages.text("properties.missing"), "notice")
        elif message is not None:
            self._show_message(render_message(self._messages, message), state.tone)
        else:
            self.message.hide()
        self.save_button.setEnabled(state.server_id is not None)
        self.reload_button.setEnabled(state.server_id is not None)

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

    def _rebuild(self, state: PropertiesState) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._editors.clear()
        self._rows.clear()
        values = dict(state.values)
        self._present = set(values)
        known = [key for key in KNOWN_PROPERTIES if key in values or not state.exists]
        others = [key for key in values if key not in KNOWN_PROPERTIES]
        row = 0
        for caption_key, keys in (("properties.known", known), ("properties.other", others)):
            if not keys:
                continue
            caption = QLabel(self._messages.text(caption_key).upper())
            caption.setObjectName("sectionCaption")
            caption.setContentsMargins(0, 12 if row else 0, 0, 4)
            self.grid.addWidget(caption, row, 0, 1, 2)
            row += 1
            for key in keys:
                self._add_row(row, key, values.get(key, ""), state.problems.get(key))
                row += 2
        self.grid.setRowStretch(row, 1)
        self._initial = self.values()
        self._apply_filter(self.filter_edit.text())

    def _add_row(self, row: int, key: str, value: str, problem: str | None) -> None:
        label = QLabel(key)
        label.setObjectName("fieldLabel")
        editor = self._editor(key, value, present=key in self._present)
        error = QLabel(self._messages.text("properties.invalid_value", name=key, reason=problem) if problem else "")
        error.setObjectName("fieldError")
        error.setVisible(bool(problem))
        self.grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignVCenter)
        self.grid.addWidget(editor, row, 1)
        self.grid.addWidget(error, row + 1, 1)
        self._editors[key] = editor
        self._rows[key] = (label, editor, error)

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

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for key, (label, editor, error) in self._rows.items():
            visible = not needle or needle in key.lower()
            label.setVisible(visible)
            editor.setVisible(visible)
            error.setVisible(visible and bool(error.text()))

    def _show_message(self, text: str, tone: str) -> None:
        self.message.setText(text)
        self.message.setProperty("tone", tone)
        style = self.message.style()
        style.unpolish(self.message)
        style.polish(self.message)
        self.message.show()

    def changed_values(self) -> dict[str, str]:
        """Return only the values the user changed since the editors were filled."""
        return {key: value for key, value in self.values().items() if self._initial.get(key) != value}

    def _on_save(self) -> None:
        self.save_requested.emit(self.changed_values())
