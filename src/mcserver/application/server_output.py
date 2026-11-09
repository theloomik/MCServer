"""Bounded console-output buffer with live subscriptions."""

import logging
from collections import deque
from collections.abc import Callable
from itertools import count
from threading import RLock

from mcserver.application.ports import OutputStream, ServerOutputLine, ServerOutputListener

DEFAULT_OUTPUT_CAPACITY = 2000

_logger = logging.getLogger(__name__)

Unsubscribe = Callable[[], None]


class ServerOutputBuffer:
    """Keep the most recent console lines and forward new ones to subscribers.

    The buffer implements the ``ServerOutputSink`` port. ``publish`` is called
    from process reader threads, so listeners run on those threads and must
    return quickly; a presentation adapter should hand lines over to its own
    thread (for example through a Qt signal) instead of doing work inline.

    Listeners are invoked while the buffer's lock is held. This guarantees that
    a subscriber with ``replay=True`` sees every buffered line exactly once and
    in order, followed by live lines, with no gap or duplicate between the two.
    """

    def __init__(self, capacity: int = DEFAULT_OUTPUT_CAPACITY) -> None:
        """Create an empty buffer that retains at most ``capacity`` lines."""
        if capacity < 1:
            raise ValueError("Output buffer capacity must be at least 1.")
        self._capacity = capacity
        self._lines: deque[ServerOutputLine] = deque(maxlen=capacity)
        self._listeners: list[ServerOutputListener] = []
        self._sequence = count(1)
        self._lock = RLock()

    @property
    def capacity(self) -> int:
        """Return the maximum number of retained lines."""
        return self._capacity

    def publish(self, server_id: str, stream: OutputStream, text: str) -> None:
        """Store one line, evicting the oldest when full, and notify listeners."""
        with self._lock:
            line = ServerOutputLine(next(self._sequence), server_id, stream, text)
            self._lines.append(line)
            for listener in tuple(self._listeners):
                self._notify(listener, line)

    def snapshot(self, server_id: str | None = None) -> tuple[ServerOutputLine, ...]:
        """Return retained lines, oldest first, optionally for one server only."""
        with self._lock:
            if server_id is None:
                return tuple(self._lines)
            return tuple(line for line in self._lines if line.server_id == server_id)

    def subscribe(self, listener: ServerOutputListener, *, replay: bool = True) -> Unsubscribe:
        """Register ``listener`` for new lines and return a function that removes it.

        With ``replay`` the listener first receives every retained line.
        Calling the returned function more than once is safe.
        """
        with self._lock:
            if replay:
                for line in tuple(self._lines):
                    self._notify(listener, line)
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def clear(self) -> None:
        """Discard retained lines; subscriptions and sequence numbering continue."""
        with self._lock:
            self._lines.clear()

    @staticmethod
    def _notify(listener: ServerOutputListener, line: ServerOutputLine) -> None:
        """Deliver one line, isolating the buffer and other listeners from failures."""
        try:
            listener(line)
        except Exception:
            _logger.exception("Server output listener failed.")
