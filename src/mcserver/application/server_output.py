"""Bounded console-output buffer with live subscriptions."""

import logging
from collections import deque
from collections.abc import Callable
from itertools import islice
from threading import Condition, Lock, Thread, current_thread

from mcserver.application.ports import OutputStream, ServerOutputLine, ServerOutputListener

DEFAULT_OUTPUT_CAPACITY = 2000

_logger = logging.getLogger(__name__)

Unsubscribe = Callable[[], None]


class _Subscription:
    """One listener and the sequence number of the last line handed to it."""

    __slots__ = ("active", "cursor", "listener")

    def __init__(self, listener: ServerOutputListener, cursor: int) -> None:
        self.listener = listener
        self.cursor = cursor
        self.active = True


class ServerOutputBuffer:
    """Keep the most recent console lines and forward them to subscribers.

    The buffer implements the ``ServerOutputSink`` port. ``publish`` only
    records a line and wakes a single dispatcher thread, so process reader
    threads never wait for listeners. Listeners run on that dispatcher thread
    with no buffer lock held: they may call any buffer method except
    ``flush`` and ``close``. A presentation adapter should still hand lines
    over to its own thread (for example through a Qt signal), because one slow
    listener delays delivery to the others.

    Delivery guarantees per subscription:

    * lines arrive in ``sequence`` order and each line at most once;
    * with ``replay=True`` the subscriber receives every retained line followed
      by every later line, with no gap or duplicate between replay and live;
    * a listener that falls more than ``capacity`` lines behind loses the
      evicted lines. The skipped range is visible as a jump in ``sequence``.
    """

    def __init__(self, capacity: int = DEFAULT_OUTPUT_CAPACITY) -> None:
        """Create an empty buffer that retains at most ``capacity`` lines."""
        if capacity < 1:
            raise ValueError("Output buffer capacity must be at least 1.")
        self._capacity = capacity
        self._lines: deque[ServerOutputLine] = deque(maxlen=capacity)
        self._last_sequence = 0
        self._subscriptions: list[_Subscription] = []
        self._lock = Lock()
        self._changed = Condition(self._lock)
        self._dispatcher: Thread | None = None
        self._delivering = False
        self._closed = False

    @property
    def capacity(self) -> int:
        """Return the maximum number of retained lines."""
        return self._capacity

    def publish(self, server_id: str, stream: OutputStream, text: str) -> None:
        """Store one line, evicting the oldest when full, and wake the dispatcher."""
        with self._lock:
            self._last_sequence += 1
            self._lines.append(ServerOutputLine(self._last_sequence, server_id, stream, text))
            self._changed.notify_all()

    def snapshot(self, server_id: str | None = None) -> tuple[ServerOutputLine, ...]:
        """Return retained lines, oldest first, optionally for one server only."""
        with self._lock:
            if server_id is None:
                return tuple(self._lines)
            return tuple(line for line in self._lines if line.server_id == server_id)

    def subscribe(self, listener: ServerOutputListener, *, replay: bool = True) -> Unsubscribe:
        """Register ``listener`` and return a function that removes it.

        With ``replay`` the listener first receives every retained line. Once
        the returned function has been called, no further delivery to the
        listener starts; calling it more than once is safe.
        """
        with self._lock:
            if self._closed:
                raise RuntimeError("Cannot subscribe to a closed output buffer.")
            subscription = _Subscription(listener, 0 if replay else self._last_sequence)
            self._subscriptions.append(subscription)
            self._start_dispatcher()
            self._changed.notify_all()

        def unsubscribe() -> None:
            with self._lock:
                subscription.active = False
                if subscription in self._subscriptions:
                    self._subscriptions.remove(subscription)
                self._changed.notify_all()

        return unsubscribe

    def clear(self) -> None:
        """Discard retained lines; subscriptions and sequence numbering continue."""
        with self._lock:
            self._lines.clear()

    def flush(self, timeout: float | None = None) -> bool:
        """Wait until every subscriber has received all published lines.

        Returns ``False`` if ``timeout`` expires first. Must not be called from
        a listener, because the dispatcher would wait for itself.
        """
        self._reject_dispatcher_thread("flush")
        with self._lock:
            return self._changed.wait_for(self._is_idle, timeout)

    def close(self, timeout: float | None = None) -> None:
        """Stop delivering to listeners and end the dispatcher thread.

        Lines already handed to a listener finish; undelivered lines are not
        delivered. ``publish`` and ``snapshot`` keep working afterwards.
        """
        self._reject_dispatcher_thread("close")
        with self._lock:
            self._closed = True
            self._changed.notify_all()
            dispatcher = self._dispatcher
        if dispatcher is not None:
            dispatcher.join(timeout)

    def _start_dispatcher(self) -> None:
        """Start the delivery thread on first subscription; caller holds the lock."""
        if self._dispatcher is None:
            self._dispatcher = Thread(target=self._dispatch_loop, name="server-output-dispatcher", daemon=True)
            self._dispatcher.start()

    def _dispatch_loop(self) -> None:
        """Deliver pending lines to each subscription outside the lock, forever."""
        while True:
            with self._lock:
                batch = self._take_pending()
                while not batch:
                    self._delivering = False
                    self._changed.notify_all()
                    if self._closed:
                        return
                    self._changed.wait()
                    batch = self._take_pending()
                self._delivering = True

            for subscription, lines in batch:
                for line in lines:
                    if not subscription.active or self._closed:
                        break
                    self._notify(subscription.listener, line)

    def _take_pending(self) -> list[tuple[_Subscription, list[ServerOutputLine]]]:
        """Collect undelivered retained lines and advance cursors; caller holds the lock."""
        if self._closed:
            return []
        batch: list[tuple[_Subscription, list[ServerOutputLine]]] = []
        first_sequence = self._lines[0].sequence if self._lines else self._last_sequence + 1
        for subscription in self._subscriptions:
            if subscription.cursor >= self._last_sequence:
                continue
            # Retained lines have consecutive sequence numbers, so the offset is direct.
            start = max(0, subscription.cursor + 1 - first_sequence)
            lines = list(islice(self._lines, start, None))
            subscription.cursor = self._last_sequence
            if lines:
                batch.append((subscription, lines))
        return batch

    def _is_idle(self) -> bool:
        """Return whether nothing is being or waiting to be delivered; caller holds the lock."""
        if self._closed:
            return not self._delivering
        return not self._delivering and all(s.cursor >= self._last_sequence for s in self._subscriptions)

    def _reject_dispatcher_thread(self, method: str) -> None:
        """Prevent a listener from blocking on its own dispatcher."""
        if current_thread() is self._dispatcher:
            raise RuntimeError(f"{method}() cannot be called from an output listener.")

    @staticmethod
    def _notify(listener: ServerOutputListener, line: ServerOutputLine) -> None:
        """Deliver one line, isolating the buffer and other listeners from failures."""
        try:
            listener(line)
        except Exception:
            _logger.exception("Server output listener failed.")
