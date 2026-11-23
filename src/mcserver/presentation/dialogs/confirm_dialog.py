"""Themed confirmation and notice dialog that replaces ``QMessageBox`` (M4 design)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from mcserver.presentation.dialogs.form import FormDialog
from mcserver.presentation.views.widgets import button


@dataclass(frozen=True, slots=True)
class Choice:
    """One button: the answer ``key`` it returns, its ``label`` and its button ``kind``."""

    key: str
    label: str
    kind: str = "secondary"


class ConfirmDialog(FormDialog):
    """Ask one question with a tone icon; ``answer`` holds the chosen key (``None`` when closed)."""

    def __init__(
        self,
        title: str,
        text: str,
        choices: Sequence[Choice],
        parent: QWidget | None = None,
        *,
        tone: str = "info",
        default: str | None = None,
    ) -> None:
        """Build the dialog; ``default`` names the choice that answers Enter (the safe one for risky questions)."""
        super().__init__(title, "", parent, tone=tone)
        self.setMinimumWidth(480)
        self.setMaximumWidth(620)
        self.answer: str | None = None
        self.text_label = QLabel(text)
        self.text_label.setObjectName("dialogSubtitle")
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.addWidget(self.text_label)
        self.buttons: dict[str, QPushButton] = {}
        for choice in choices:
            widget = button(choice.label, choice.kind)
            widget.clicked.connect(lambda _checked=False, key=choice.key: self._choose(key))
            self.buttons[choice.key] = widget
        default_button = self.buttons.get(default) if default else None
        self.add_buttons(*self.buttons.values(), default=default_button)
        if default_button is not None:
            default_button.setFocus()

    def _choose(self, key: str) -> None:
        self.answer = key
        self.accept()


def ask(
    parent: QWidget | None,
    title: str,
    text: str,
    choices: Sequence[Choice],
    *,
    tone: str = "info",
    default: str | None = None,
) -> str | None:
    """Show a ``ConfirmDialog`` modally and return the chosen key, or ``None`` when it was closed."""
    dialog = ConfirmDialog(title, text, choices, parent, tone=tone, default=default)
    dialog.exec()
    answer = dialog.answer
    dialog.deleteLater()
    return answer


__all__ = ["Choice", "ConfirmDialog", "ask"]
