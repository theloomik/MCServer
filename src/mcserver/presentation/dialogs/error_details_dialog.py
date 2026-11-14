"""Read-only dialog with the technical details of an error (exit code, last console lines)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mcserver.presentation import theme
from mcserver.presentation.errors import UserMessage, render_message
from mcserver.presentation.i18n import Messages


class ErrorDetailsDialog(QDialog):
    """Show the message and its untranslated details, with a Copy button."""

    def __init__(self, message: UserMessage, messages: Messages, parent: QWidget | None = None) -> None:
        """Build the dialog for ``message``."""
        super().__init__(parent)
        self.setWindowTitle(messages.text("details.title"))
        self.setStyleSheet(theme.STYLESHEET)
        self.resize(760, 460)
        summary = QLabel(render_message(messages, message))
        summary.setWordWrap(True)
        self.details = QPlainTextEdit(message.details)
        self.details.setObjectName("console")
        self.details.setReadOnly(True)
        self.copy_button = QPushButton(messages.text("details.copy"))
        self.copy_button.clicked.connect(self._copy)
        close_button = QPushButton(messages.text("details.close"))
        close_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(close_button)
        layout = QVBoxLayout(self)
        layout.addWidget(summary)
        layout.addWidget(self.details, 1)
        layout.addLayout(buttons)

    def _copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.details.toPlainText())
