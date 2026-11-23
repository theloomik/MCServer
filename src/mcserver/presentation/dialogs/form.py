"""Shared layout for MCServer form dialogs: a card with a title, labelled fields and buttons."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QLayout, QPushButton, QVBoxLayout, QWidget

from mcserver.presentation import theme


class FormDialog(QDialog):
    """A dialog whose content is a card; subclasses add fields with ``add_field``."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        """Build the card with ``title`` and an optional ``subtitle``."""
        super().__init__(parent)
        self.setObjectName("formDialog")
        self.setStyleSheet(theme.STYLESHEET)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        heading = QLabel(title)
        heading.setObjectName("dialogTitle")
        self.card = QFrame()
        self.card.setProperty("card", True)
        self.body = QVBoxLayout(self.card)
        self.body.setContentsMargins(32, 28, 32, 28)
        self.body.setSpacing(6)
        self.body.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("fieldHint")
            sub.setWordWrap(True)
            self.body.addWidget(sub)
        self.body.addSpacing(12)
        self.error_label = QLabel()
        self.error_label.setObjectName("fieldError")
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.error_label.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.card)

    def add_field(self, label: str, editor: QWidget | QLayout, hint: str = "") -> QLabel | None:
        """Add a labelled field; return its hint label (so callers can change it) or ``None``."""
        caption = QLabel(label)
        caption.setObjectName("formLabel")
        self.body.addWidget(caption)
        if isinstance(editor, QLayout):
            self.body.addLayout(editor)
        else:
            self.body.addWidget(editor)
        hint_label: QLabel | None = None
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("fieldHint")
            hint_label.setWordWrap(True)
            self.body.addWidget(hint_label)
        self.body.addSpacing(10)
        return hint_label

    def add_note(self, text: str) -> QLabel:
        """Add a wrapped explanatory line."""
        note = QLabel(text)
        note.setObjectName("fieldHint")
        note.setWordWrap(True)
        self.body.addWidget(note)
        return note

    def add_buttons(self, *buttons: QPushButton) -> None:
        """Add the error line and the button row (the last button is the default)."""
        self.body.addWidget(self.error_label)
        row = QHBoxLayout()
        row.addStretch(1)
        for button in buttons:
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(button)
        if buttons:
            buttons[-1].setDefault(True)
        self.body.addSpacing(8)
        self.body.addLayout(row)

    def show_error(self, text: str | None) -> None:
        """Show ``text`` above the buttons, or hide the error line for ``None``."""
        self.error_label.setText(text or "")
        self.error_label.setVisible(bool(text))


def primary_button(text: str) -> QPushButton:
    """Return an accent button."""
    button = QPushButton(text)
    button.setObjectName("primaryButton")
    return button


def secondary_button(text: str) -> QPushButton:
    """Return a neutral button."""
    button = QPushButton(text)
    button.setObjectName("secondaryButton")
    return button
