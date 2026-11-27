"""Shared dialog layout from the M4 design: header (optional tone icon), body, footer with error line and buttons."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mcserver.presentation import icons, theme
from mcserver.presentation.views.widgets import button

TONES = ("info", "warning", "danger", "success")


def tone_style(tone: str) -> tuple[str, str, str]:
    """Return (icon, icon colour, tile colour) of a header ``tone`` in the current theme."""
    return {
        "info": ("info", theme.INFO, theme.INFO_SUBTLE),
        "warning": ("alert", theme.WARNING_TEXT, theme.WARNING_SUBTLE),
        "danger": ("alert", theme.DANGER_TEXT, theme.DANGER_SUBTLE),
        "success": ("check", theme.ACCENT_HOVER, theme.ACCENT_SUBTLE),
    }[tone]


class FormDialog(QDialog):
    """A dialog whose content is a card; subclasses add fields with ``add_field`` and finish with ``add_buttons``."""

    def __init__(
        self, title: str, subtitle: str = "", parent: QWidget | None = None, *, tone: str | None = None
    ) -> None:
        """Build the card with ``title``, an optional ``subtitle`` and an optional header ``tone`` icon."""
        super().__init__(parent)
        self.setObjectName("formDialog")
        self.setStyleSheet(theme.STYLESHEET)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self.card = QFrame()
        self.card.setObjectName("dialogCard")

        heading = QLabel(title)
        heading.setObjectName("dialogTitle")
        heading.setWordWrap(True)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(heading)
        self.subtitle_label: QLabel | None = None
        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setObjectName("dialogSubtitle")
            self.subtitle_label.setWordWrap(True)
            self.subtitle_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            titles.addWidget(self.subtitle_label)
        header = QHBoxLayout()
        header.setSpacing(14)
        if tone in TONES:
            icon_name, color, tile_color = tone_style(tone)
            tile = QLabel()
            tile.setObjectName("dialogTone")
            tile.setFixedSize(36, 36)
            tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tile.setStyleSheet(f"background-color: {tile_color}; border-radius: 8px;")
            tile.setPixmap(icons.pixmap(icon_name, color, 18))
            # Beside a one-line title the icon is centred; with a subtitle it lines up with the title.
            header.addWidget(tile, 0, Qt.AlignmentFlag.AlignTop if subtitle else Qt.AlignmentFlag.AlignVCenter)
        header.addLayout(titles, 1)

        self.body = QVBoxLayout()
        self.body.setSpacing(6)
        self.error_label = QLabel()
        self.error_label.setObjectName("fieldError")
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.error_label.hide()

        content = QVBoxLayout()
        content.setContentsMargins(28, 24, 28, 18)
        content.setSpacing(16)
        content.addLayout(header)
        content.addLayout(self.body)
        self.footer = QFrame()
        self.footer.setObjectName("dialogFooter")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(28, 12, 20, 12)
        self.footer_layout.setSpacing(8)
        self.footer.hide()

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        card_layout.addLayout(content, 1)
        card_layout.addWidget(self.footer)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.card)

    def add_field(self, label: str, editor: QWidget | QLayout, hint: str = "") -> QLabel | None:
        """Add a labelled field; return its hint label (so callers can change it) or ``None``."""
        caption = QLabel(label)
        caption.setObjectName("formLabel")
        field = editor if isinstance(editor, QWidget) else _first_input(editor)
        if field is not None:
            # Screen readers announce the field with its label; Alt+mnemonic in the label focuses it.
            caption.setBuddy(field)
            if not field.accessibleName():
                field.setAccessibleName(label.replace("&", ""))
            if hint:
                field.setAccessibleDescription(hint)
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

    def add_buttons(self, *buttons: QPushButton, default: QPushButton | None = None) -> None:
        """Put the error line and ``buttons`` in the footer; ``default`` (else the last button) answers Enter."""
        self.body.addWidget(self.error_label)
        self.footer_layout.addStretch(1)
        for widget in buttons:
            widget.setCursor(Qt.CursorShape.PointingHandCursor)
            self.footer_layout.addWidget(widget)
        chosen = default or (buttons[-1] if buttons else None)
        if chosen is not None:
            chosen.setDefault(True)
        self.footer.show()

    def show_error(self, text: str | None) -> None:
        """Show ``text`` above the buttons, or hide the error line for ``None``."""
        self.error_label.setText(text or "")
        self.error_label.setVisible(bool(text))


def _first_input(layout: QLayout) -> QWidget | None:
    """Return the first focusable widget in ``layout`` (the field a row of widgets is about)."""
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if widget is not None and widget.focusPolicy() != Qt.FocusPolicy.NoFocus:
            return widget
        child = item.layout() if item is not None else None
        if child is not None and (found := _first_input(child)) is not None:
            return found
    return None


def primary_button(text: str, icon_name: str | None = None) -> QPushButton:
    """Return an accent button."""
    return button(text, "primary", icon_name)


def secondary_button(text: str, icon_name: str | None = None) -> QPushButton:
    """Return a neutral button."""
    return button(text, "secondary", icon_name)


def danger_button(text: str, icon_name: str | None = None) -> QPushButton:
    """Return a button for a destructive or forceful action."""
    return button(text, "danger", icon_name)
