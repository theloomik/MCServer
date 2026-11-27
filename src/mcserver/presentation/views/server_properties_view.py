"""Editor for ``server.properties`` (UX overhaul): grouped rows with readable names, typed editors, search."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
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
from mcserver.presentation import icons, theme
from mcserver.presentation.controllers.properties import PropertiesState
from mcserver.presentation.errors import render_message
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.widgets import Banner, button, caption, icon_label, panel_bar, repolish

Editor = QCheckBox | QComboBox | QSpinBox | QLineEdit
EDITOR_WIDTH = 220
CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "common",
        (
            "motd",
            "gamemode",
            "difficulty",
            "max-players",
            "pvp",
            "hardcore",
            "white-list",
            "enforce-whitelist",
            "online-mode",
        ),
    ),
    (
        "world",
        (
            "level-name",
            "level-seed",
            "view-distance",
            "simulation-distance",
            "spawn-protection",
            "max-world-size",
            "allow-nether",
            "spawn-monsters",
            "allow-flight",
            "force-gamemode",
            "enable-command-block",
            "player-idle-timeout",
        ),
    ),
    ("network", ("server-port", "server-ip", "enable-query", "query.port", "enable-rcon", "rcon.port")),
)
"""Known properties by group, most used first; anything else goes to the collapsed "Other" group."""


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
        self._labels: dict[str, str] = {}
        self._groups: list[tuple[QWidget, QFrame, list[str]]] = []
        self.other_button: QPushButton | None = None
        self._present: set[str] = set()
        self._server_id: str | None = None

        toolbar, bar = panel_bar("top")
        title = QLabel(messages.text("properties.title"))
        title.setObjectName("monoTitle")
        self.unsaved_label = QLabel()
        self.unsaved_label.setObjectName("unsavedCount")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(messages.text("properties.search"))
        self.filter_edit.setAccessibleName(messages.text("properties.search"))
        self.filter_edit.setMinimumWidth(120)  # shrinks in a narrow window instead of widening it
        self.filter_edit.setMaximumWidth(220)
        self.filter_edit.addAction(icons.icon("search", theme.TEXT_MUTED), QLineEdit.ActionPosition.LeadingPosition)
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
        self.content_layout.setContentsMargins(20, 12, 20, 20)
        self.content_layout.setSpacing(8)
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
        self._labels.clear()
        self._groups.clear()
        self.other_button = None

    def _rebuild(self, state: PropertiesState) -> None:
        self._clear()
        values = dict(state.values)
        self._present = set(values)
        grouped = {key for _name, keys in CATEGORIES for key in keys}
        groups: list[tuple[str, list[str]]] = [
            (name, [key for key in keys if key in values or (not state.exists and key in KNOWN_PROPERTIES)])
            for name, keys in CATEGORIES
        ]
        extra_known = [key for key in KNOWN_PROPERTIES if key not in grouped and (key in values or not state.exists)]
        if extra_known:
            groups[0][1].extend(extra_known)
        others = [key for key in values if key not in KNOWN_PROPERTIES]
        groups.append(("other", others))
        for name, keys in groups:
            if keys:
                self._group(name, keys, values, state.problems)
        self.content_layout.addStretch(1)
        self._initial = self.values()
        self._apply_filter(self.filter_edit.text())

    def _group(self, name: str, keys: list[str], values: dict[str, str], problems: Mapping[str, str]) -> None:
        """Add a titled group of rows; "other" starts collapsed (its keys are rare and technical)."""
        heading = QWidget()
        heading_row = QHBoxLayout(heading)
        heading_row.setContentsMargins(0, 10, 0, 2)
        title = caption(self._messages.text(f"properties.group.{name}"))
        heading_row.addWidget(title, 1)
        frame = QFrame()
        frame.setObjectName("settingsGroup")
        rows = QVBoxLayout(frame)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)
        for key in keys:
            rows.addWidget(self._cell(key, values.get(key, ""), problems.get(key), first=rows.count() == 0))
        if name == "other":
            toggle = QPushButton(self._messages.plural("properties.other_count", len(keys)))
            toggle.setObjectName("disclosureButton")
            toggle.setCheckable(True)
            toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle.toggled.connect(lambda _shown: self._apply_filter(self.filter_edit.text()))
            toggle.toggled.connect(lambda shown: toggle.setIcon(icons.icon("chevron-up" if shown else "chevron-down")))
            toggle.setIcon(icons.icon("chevron-down"))
            heading_row.addWidget(toggle)
            self.other_button = toggle
        self.content_layout.addWidget(heading)
        self.content_layout.addWidget(frame)
        self._groups.append((heading, frame, keys))

    def _cell(self, key: str, value: str, problem: str | None, *, first: bool = False) -> QWidget:
        """One property: its readable name and technical key on the left, the editor on the right."""
        cell = QFrame()
        cell.setObjectName("settingsRow")
        cell.setProperty("first", first)
        friendly = self._messages.text(f"properties.label.{key}") if key in KNOWN_PROPERTIES else key
        self._labels[key] = friendly
        # Every child gets its row as parent at once: a parentless widget made visible is a window of its own
        # and flashes on screen until the layout adopts it.
        label = QLabel(friendly, cell)
        label.setObjectName("settingTitle")
        label.setProperty("invalid", bool(problem))
        technical = QLabel(key, cell)
        technical.setObjectName("propertyKey")
        technical.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        technical.setVisible(friendly != key)
        editor = self._editor(key, value, present=key in self._present)
        editor.setProperty("invalid", bool(problem))
        label.setBuddy(editor)
        editor.setAccessibleName(friendly)
        editor.setAccessibleDescription(key)
        message = self._messages.text("properties.invalid_value", name=key, reason=problem) if problem else ""
        if problem:
            editor.setAccessibleDescription(message)
        if not isinstance(editor, QCheckBox):
            editor.setFixedWidth(EDITOR_WIDTH)
        self._watch(editor)
        error = QLabel(message, cell)
        error.setObjectName("fieldError")
        error.setWordWrap(True)
        error.setVisible(bool(problem))
        texts = QVBoxLayout()
        texts.setSpacing(1)
        texts.addWidget(label)
        texts.addWidget(technical)
        texts.addWidget(error)
        line = QHBoxLayout(cell)
        line.setContentsMargins(16, 9, 16, 9)
        line.setSpacing(16)
        line.addLayout(texts, 1)
        line.addWidget(editor, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        repolish(cell)
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
        """Show the rows whose readable name or key contains ``text``; searching opens the "Other" group."""
        needle = text.strip().lower()
        for key, cell in self._cells.items():
            cell.setVisible(not needle or needle in key.lower() or needle in self._labels.get(key, "").lower())
        other_open = self.other_button is not None and self.other_button.isChecked()
        for heading, frame, keys in self._groups:
            matches = any(not self._cells[key].isHidden() for key in keys)
            is_other = self.other_button is not None and heading.isAncestorOf(self.other_button)
            frame.setVisible(matches and (not is_other or other_open or bool(needle)))
            heading.setVisible(matches)

    def _show_message(self, text: str, tone: str) -> None:
        self.message_banner.show_message(text, tone)
        repolish(self.message)

    def _on_save(self) -> None:
        self.save_requested.emit(self.changed_values())
