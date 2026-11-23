"""Console card: server output with stderr highlighting, follow mode and command input."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
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
from mcserver.presentation.controllers.console import ConsoleLine, LineLevel
from mcserver.presentation.i18n import Messages

MAX_CONSOLE_LINES = 5000
MAX_HISTORY = 100
FILTERS = ("all", "warnings")
"""Console filters; each has the label key ``console.filter.<name>``."""


class CommandInput(QLineEdit):
    """Command field with shell-like history: Up and Down walk through earlier commands."""

    def __init__(self) -> None:
        """Start with an empty history."""
        super().__init__()
        self.history: list[str] = []
        self._position = 0
        self._draft = ""

    def remember(self, command: str) -> None:
        """Add ``command`` to the history (repeats of the last one are kept once)."""
        if not self.history or self.history[-1] != command:
            self.history.append(command)
            del self.history[:-MAX_HISTORY]
        self._position = len(self.history)
        self._draft = ""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        """Handle Up and Down; everything else is normal editing."""
        key = event.key()
        if key == Qt.Key.Key_Up and self.history:
            if self._position == len(self.history):
                self._draft = self.text()
            self._position = max(0, self._position - 1)
            self.setText(self.history[self._position])
            return
        if key == Qt.Key.Key_Down and self._position < len(self.history):
            self._position += 1
            at_end = self._position == len(self.history)
            self.setText(self._draft if at_end else self.history[self._position])
            return
        super().keyPressEvent(event)


class ServerConsoleView(QFrame):
    """Show console lines and send commands while the server is running.

    New lines scroll into view only while the user is at the bottom, so
    reading older output is not interrupted. Text can be selected and copied.
    """

    clear_requested = Signal()
    save_requested = Signal()
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
        self.save_button = QPushButton(messages.text("console.save"))
        self.save_button.setObjectName("clearConsole")
        self.save_button.clicked.connect(self.save_requested)
        self.filter_combo = QComboBox()
        for name in FILTERS:
            self.filter_combo.addItem(messages.text(f"console.filter.{name}"), name)
        self.filter_combo.currentIndexChanged.connect(self._refilter)
        self._lines: deque[ConsoleLine] = deque(maxlen=MAX_CONSOLE_LINES)
        header = QHBoxLayout()
        header.addWidget(title, 1)
        header.addWidget(self.filter_combo)
        header.addWidget(self.save_button)
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
        for control in (self.clear_button, self.save_button, self.filter_combo):
            control.setEnabled(available)

        self._normal = QTextCharFormat()
        self._normal.setForeground(QColor(theme.CONSOLE_TEXT))
        self._error = QTextCharFormat()
        self._error.setForeground(QColor(theme.CONSOLE_ERROR))
        self._command = QTextCharFormat()
        self._command.setForeground(QColor(theme.ACCENT))
        self._warning = QTextCharFormat()
        self._warning.setForeground(QColor(theme.WARNING))

        self.input = CommandInput()
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
        self._lines.extend(lines)
        self._render(tuple(line for line in lines if self._shown(line)))

    def _shown(self, line: ConsoleLine) -> bool:
        return self.filter_combo.currentData() != "warnings" or line.level is not LineLevel.INFO

    def _refilter(self) -> None:
        self.text.clear()
        self._render(tuple(line for line in self._lines if self._shown(line)))

    def _render(self, lines: tuple[ConsoleLine, ...]) -> None:
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
                cursor.insertText(line.text, self._format(line))
        cursor.endEditBlock()
        if follow:
            scrollbar.setValue(scrollbar.maximum())

    def _format(self, line: ConsoleLine) -> QTextCharFormat:
        level = line.level
        if level is LineLevel.ERROR:
            return self._error
        return self._warning if level is LineLevel.WARNING else self._normal

    def set_input_enabled(self, enabled: bool) -> None:
        """Allow typing commands only while the server can receive them."""
        self.input.setEnabled(enabled)
        self.send_button.setEnabled(enabled)

    def _submit(self) -> None:
        command = self.input.text().strip()
        if not command or not self.input.isEnabled():
            return
        self.input.remember(command)
        self.input.clear()
        self.command_submitted.emit(command)

    def clear(self) -> None:
        """Remove all displayed text."""
        self._lines.clear()
        self.text.clear()

    def plain_text(self) -> str:
        """Return the displayed text."""
        return self.text.toPlainText()

    def log_text(self) -> str:
        """Return every kept line, unfiltered, for saving (commands are marked with ``> ``)."""
        return "\n".join(f"> {line.text}" if line.is_command else line.text for line in self._lines) + "\n"
