"""Read-only dialog with the technical details of an error (exit code, last console lines)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPlainTextEdit, QWidget

from mcserver.presentation.dialogs.form import FormDialog, primary_button, secondary_button
from mcserver.presentation.errors import UserMessage, render_message
from mcserver.presentation.i18n import Messages


class ErrorDetailsDialog(FormDialog):
    """Show the message and its untranslated details, with a Copy button."""

    def __init__(self, message: UserMessage, messages: Messages, parent: QWidget | None = None) -> None:
        """Build the dialog for ``message``."""
        super().__init__(messages.text("details.title"), render_message(messages, message), parent, tone="danger")
        self.resize(760, 480)
        self.details = QPlainTextEdit(message.details)
        self.details.setObjectName("console")
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(260)
        self.body.addWidget(self.details, 1)
        self.copy_button = secondary_button(messages.text("details.copy"), "copy")
        self.copy_button.clicked.connect(self._copy)
        close_button = primary_button(messages.text("details.close"))
        close_button.clicked.connect(self.accept)
        self.add_buttons(self.copy_button, close_button)

    def _copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.details.toPlainText())
