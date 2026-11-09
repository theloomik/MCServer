"""Moves server output from the buffer's dispatcher thread to the GUI thread."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from mcserver.application.ports import ServerOutputLine
from mcserver.application.server_output import ServerOutputBuffer, Unsubscribe

_logger = logging.getLogger(__name__)


class OutputBridge(QObject):
    """Subscribe to ``ServerOutputBuffer`` and re-emit each line as a Qt signal.

    The subscription callback runs on the buffer's dispatcher thread and only
    emits ``line_received``; receivers must connect with a queued connection
    so widgets are touched on the GUI thread only. Every ``attach`` starts a new
    generation, so lines still queued from an earlier subscription can be
    recognised and ignored.
    """

    line_received = Signal(int, object)  # generation, ServerOutputLine

    def __init__(self, output: ServerOutputBuffer, parent: QObject | None = None) -> None:
        """Bridge ``output``; nothing is subscribed until ``attach``."""
        super().__init__(parent)
        self._output = output
        self._unsubscribe: Unsubscribe | None = None
        self._generation = 0

    @property
    def generation(self) -> int:
        """Return the generation of the current (or last) subscription."""
        return self._generation

    @property
    def attached(self) -> bool:
        """Return whether a subscription is active."""
        return self._unsubscribe is not None

    def attach(self) -> int:
        """Subscribe with replay of retained lines and return the new generation."""
        self.detach()
        self._generation += 1
        generation = self._generation

        def forward(line: ServerOutputLine) -> None:
            try:
                self.line_received.emit(generation, line)
            except RuntimeError:  # the Qt object was already deleted; nothing left to notify
                _logger.debug("Output bridge was deleted before a line could be forwarded.")

        self._unsubscribe = self._output.subscribe(forward, replay=True)
        return generation

    def detach(self) -> None:
        """End the subscription; safe to call repeatedly."""
        unsubscribe, self._unsubscribe = self._unsubscribe, None
        if unsubscribe is not None:
            unsubscribe()
