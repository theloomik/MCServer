"""Console card: server output with stderr highlighting, follow mode and command input."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
)

from mcserver.presentation import theme
from mcserver.presentation.controllers.console import ConsoleLine
from mcserver.presentation.i18n import Messages

MAX_CONSOLE_LINES = 5000


class ServerConsoleView(QFrame):
    """Show console lines and send commands while the server is running.

    New lines scroll into view only while the user is at the bottom, so
    reading older output is not interrupted. Text can be selected and copied.
    """

    clear_requested = Signal()
    command_submitted = Signal(str)

    def __init__(self, messages: Messages, available: bool) -> None:
        """Build the console; ``available`` is ``False`` when output cannot exist (Java missing)."""
        super().__init__()
        self.setProperty("card", True)
        self.setObjectName("consoleCard")

        title = QLabel(messages.text("console.title"))
        title.setObjectName("consoleTitle")
        self.clear_button = QPushButton(messages.text("console.clear"))
        self.clear_button.setObjectName("clearConsole")
        self.clear_button.clicked.connect(self.clear_requested)
        header = QHBoxLayout()
        header.addWidget(title, 1)
        header.addWidget(self.clear_button)

        self.text = QPlainTextEdit()
        self.text.setObjectName("console")
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(MAX_CONSOLE_LINES)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text.setPlaceholderText(messages.text("console.placeholder"))
        self.text.setUndoRedoEnabled(False)

        self.unavailable_label = QLabel(messages.text("console.unavailable"))
        self.unavailable_label.setObjectName("consoleUnavailable")
        self.unavailable_label.setWordWrap(True)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.text)
        self.pages.addWidget(self.unavailable_label)
        self.pages.setCurrentWidget(self.text if available else self.unavailable_label)
        self.clear_button.setEnabled(available)

        self._normal = QTextCharFormat()
        self._normal.setForeground(QColor(theme.CONSOLE_TEXT))
        self._error = QTextCharFormat()
        self._error.setForeground(QColor(theme.CONSOLE_ERROR))
        self._command = QTextCharFormat()
        self._command.setForeground(QColor(theme.ACCENT))

        self.input = QLineEdit()
        self.input.setObjectName("consoleInput")
        self.input.setPlaceholderText(messages.text("console.input.placeholder"))
        self.input.returnPressed.connect(self._submit)
        self.send_button = QPushButton(messages.text("console.send"))
        self.send_button.setObjectName("consoleSend")
        self.send_button.clicked.connect(self._submit)
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_button)
        self.set_input_enabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.pages, 1)
        layout.addLayout(input_row)

    def append_lines(self, lines: tuple[ConsoleLine, ...]) -> None:
        """Append a batch, following the end only if the view was already at the bottom."""
        if not lines:
            return
        scrollbar = self.text.verticalScrollBar()
        follow = scrollbar.value() >= scrollbar.maximum() - 4
        cursor = QTextCursor(self.text.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.beginEditBlock()
        for line in lines:
            if not self.text.document().isEmpty():
                cursor.insertBlock()
            if line.is_command:
                cursor.insertText(f"> {line.text}", self._command)
            else:
                cursor.insertText(line.text, self._error if line.is_error else self._normal)
        cursor.endEditBlock()
        if follow:
            scrollbar.setValue(scrollbar.maximum())

    def set_input_enabled(self, enabled: bool) -> None:
        """Allow typing commands only while the server can receive them."""
        self.input.setEnabled(enabled)
        self.send_button.setEnabled(enabled)

    def _submit(self) -> None:
        command = self.input.text().strip()
        if not command or not self.input.isEnabled():
            return
        self.input.clear()
        self.command_submitted.emit(command)

    def clear(self) -> None:
        """Remove all displayed text."""
        self.text.clear()

    def plain_text(self) -> str:
        """Return the displayed text."""
        return self.text.toPlainText()
