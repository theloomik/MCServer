"""Console card (M4 design): toolbar, output with dimmed prefixes and level colours, command row."""

from __future__ import annotations

import re
from collections import deque

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
)

from mcserver.presentation import theme
from mcserver.presentation.controllers.console import ConsoleLine, LineLevel
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.widgets import button, icon_label, panel_bar

MAX_CONSOLE_LINES = 5000
MAX_HISTORY = 100
_PREFIX = re.compile(r"^\[[^\]]*\]:?")
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
        self._messages = messages

        toolbar, bar = panel_bar("top")
        title = QLabel(messages.text("console.title"))
        title.setObjectName("consoleTitle")
        self.count_label = QLabel()
        self.count_label.setObjectName("panelCount")
        # The count may be cut off in a narrow window; the toolbar's buttons may not.
        self.count_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.clear_button = button(messages.text("console.clear"), "ghost", "close", "clearConsole")
        self.clear_button.clicked.connect(self.clear_requested)
        self.save_button = button(messages.text("console.save"), "ghost", "save", "clearConsole")
        self.save_button.clicked.connect(self.save_requested)
        self.filter_combo = QComboBox()
        self.filter_combo.setMinimumWidth(120)
        self.filter_combo.setMaximumWidth(170)
        self.filter_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.filter_combo.setMinimumContentsLength(10)
        self.filter_combo.setAccessibleName(messages.text("a11y.console_filter"))
        for name in FILTERS:
            self.filter_combo.addItem(messages.text(f"console.filter.{name}"), name)
        self.filter_combo.currentIndexChanged.connect(self._refilter)
        self._lines: deque[ConsoleLine] = deque(maxlen=MAX_CONSOLE_LINES)
        bar.addWidget(icon_label("terminal"))
        bar.addWidget(title)
        bar.addWidget(self.count_label, 1)
        bar.addWidget(self.filter_combo)
        bar.addWidget(self.save_button)
        bar.addWidget(self.clear_button)

        self.text = QPlainTextEdit()
        self.text.setObjectName("console")
        self.text.setAccessibleName(messages.text("a11y.console_output"))
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(MAX_CONSOLE_LINES)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text.setPlaceholderText(messages.text("console.placeholder"))
        self.text.setUndoRedoEnabled(False)
        self.text.setFrameShape(QFrame.Shape.NoFrame)

        self.unavailable_label = QLabel(messages.text("console.unavailable"))
        self.unavailable_label.setObjectName("consoleUnavailable")
        self.unavailable_label.setWordWrap(True)
        self.unavailable_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.text)
        self.pages.addWidget(self.unavailable_label)
        self.pages.setCurrentWidget(self.text if available else self.unavailable_label)
        for control in (self.clear_button, self.save_button, self.filter_combo):
            control.setEnabled(available)

        self._normal = self._char_format(theme.CONSOLE_TEXT)
        self._dim = self._char_format(theme.CONSOLE_TIMESTAMP)
        self._error = self._char_format(theme.DANGER_TEXT)
        self._command = self._char_format(theme.CONSOLE_COMMAND)
        self._warning = self._char_format(theme.WARNING_TEXT)

        command_bar, row = panel_bar("bottom")
        row.setContentsMargins(12, 8, 8, 8)
        self.prompt = QLabel(messages.text("console.prompt"))
        self.prompt.setObjectName("consolePrompt")
        self.input = CommandInput()
        self.input.setObjectName("consoleInput")
        self.input.setAccessibleName(messages.text("a11y.console_command"))
        self.prompt.setBuddy(self.input)
        self.input.returnPressed.connect(self._submit)
        self.send_button = button(messages.text("console.send"), "secondary", None, "consoleSend")
        self.send_button.clicked.connect(self._submit)
        row.addWidget(self.prompt)
        row.addWidget(self.input, 1)
        row.addWidget(self.send_button)
        self.set_input_enabled(False)
        self._update_count()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(self.pages, 1)
        layout.addWidget(command_bar)

    @staticmethod
    def _char_format(color: str) -> QTextCharFormat:
        result = QTextCharFormat()
        result.setForeground(QColor(color))
        return result

    def _update_count(self) -> None:
        count = len(self._lines)
        self.count_label.setText(self._messages.text("console.line_count", count=count) if count else "")

    def append_lines(self, lines: tuple[ConsoleLine, ...]) -> None:
        """Append a batch, following the end only if the view was already at the bottom."""
        self._lines.extend(lines)
        self._render(tuple(line for line in lines if self._shown(line)))
        self._update_count()

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
                continue
            body = self._format(line)
            prefix = _PREFIX.match(line.text)
            if prefix is None:
                cursor.insertText(line.text, body)
                continue
            # "[18:02:10 INFO]:" is dimmed; a warning or error level keeps its colour.
            cursor.insertText(prefix.group(0), self._dim if body is self._normal else body)
            cursor.insertText(line.text[prefix.end() :], body)
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
        self.prompt.setEnabled(enabled)
        key = "console.input.placeholder" if enabled else "console.input.disabled"
        self.input.setPlaceholderText(self._messages.text(key))

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
        self._update_count()

    def plain_text(self) -> str:
        """Return the displayed text."""
        return self.text.toPlainText()

    def log_text(self) -> str:
        """Return every kept line, unfiltered, for saving (commands are marked with ``> ``)."""
        return "\n".join(f"> {line.text}" if line.is_command else line.text for line in self._lines) + "\n"
