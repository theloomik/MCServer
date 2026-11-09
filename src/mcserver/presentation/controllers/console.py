"""Read-only console: output of the selected server, batched for the GUI thread."""

from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from mcserver.application.ports import OutputStream, ServerOutputLine
from mcserver.presentation.adapters.output_bridge import OutputBridge

FLUSH_INTERVAL_MS = 50

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


@dataclass(frozen=True, slots=True)
class ConsoleLine:
    """One line ready for display (terminal colour codes removed)."""

    sequence: int
    is_error: bool
    text: str


class ConsoleController(QObject):
    """Feed the console view with the selected server's output.

    Subscribes through ``OutputBridge`` with replay, so switching to a server
    shows its retained history first. Lines arrive through a queued
    connection and are flushed to the view in batches. ``clear`` only hides
    what was shown so far; the shared output buffer is never cleared.
    stdout and stderr have no reliable relative order, so lines are shown in
    ``sequence`` order as delivered.
    """

    lines_appended = Signal(object)  # tuple[ConsoleLine, ...]
    cleared = Signal()

    def __init__(
        self, bridge: OutputBridge | None, flush_interval_ms: int = FLUSH_INTERVAL_MS, parent: QObject | None = None
    ) -> None:
        """Use ``bridge``; ``None`` means no output is available (Java missing)."""
        super().__init__(parent)
        self._bridge = bridge
        self._server_id: str | None = None
        self._generation = 0
        self._last_sequence = 0
        self._cleared_through: dict[str, int] = {}
        self._pending: list[ConsoleLine] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(flush_interval_ms)
        self._timer.timeout.connect(self.flush)
        if bridge is not None:
            bridge.line_received.connect(self._on_line, Qt.ConnectionType.QueuedConnection)

    @property
    def available(self) -> bool:
        """Return whether server output can be shown at all."""
        return self._bridge is not None

    @property
    def server_id(self) -> str | None:
        """Return the server whose output is shown."""
        return self._server_id

    def show_server(self, server_id: str | None) -> None:
        """Show ``server_id``'s output (with history); ``None`` stops listening."""
        if server_id == self._server_id:
            return
        self._server_id = server_id
        self._pending.clear()
        self._timer.stop()
        self._last_sequence = self._cleared_through.get(server_id, 0) if server_id else 0
        self.cleared.emit()
        if self._bridge is None:
            return
        if server_id is None:
            self._bridge.detach()
            self._generation = 0
        else:
            self._generation = self._bridge.attach()

    def clear(self) -> None:
        """Clear the visible console only; later lines keep appearing."""
        self.flush()
        if self._server_id is not None:
            self._cleared_through[self._server_id] = self._last_sequence
        self.cleared.emit()

    def close(self) -> None:
        """Stop listening; call before the window goes away."""
        self._timer.stop()
        self._pending.clear()
        if self._bridge is not None:
            self._bridge.detach()
        self._generation = 0

    @Slot()
    def flush(self) -> None:
        """Hand pending lines to the view now."""
        self._timer.stop()
        if not self._pending:
            return
        batch = tuple(sorted(self._pending, key=lambda line: line.sequence))
        self._pending.clear()
        self.lines_appended.emit(batch)

    @Slot(int, object)
    def _on_line(self, generation: int, line: ServerOutputLine) -> None:
        if generation != self._generation or line.server_id != self._server_id:
            return  # queued from an earlier subscription or another server
        if line.sequence <= self._last_sequence:
            return  # already shown or cleared
        self._last_sequence = line.sequence
        self._pending.append(
            ConsoleLine(line.sequence, line.stream is OutputStream.STDERR, _ANSI_ESCAPE.sub("", line.text))
        )
        if not self._timer.isActive():
            self._timer.start()
