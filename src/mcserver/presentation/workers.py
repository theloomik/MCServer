"""Run blocking backend calls on a thread pool and hand results back to the GUI thread."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot

_logger = logging.getLogger(__name__)

SuccessHandler = Callable[[Any], None]
ErrorHandler = Callable[[BaseException], None]


class _Relay(QObject):
    """Lives on the GUI thread; queued signals make the callbacks run there."""

    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, on_success: SuccessHandler, on_error: ErrorHandler, done: Callable[[_Relay], None]) -> None:
        super().__init__()
        self._on_success = on_success
        self._on_error = on_error
        self._done = done
        self.succeeded.connect(self._deliver_success, Qt.ConnectionType.QueuedConnection)
        self.failed.connect(self._deliver_error, Qt.ConnectionType.QueuedConnection)

    @Slot(object)
    def _deliver_success(self, result: object) -> None:
        try:
            self._on_success(result)
        finally:
            self._done(self)

    @Slot(object)
    def _deliver_error(self, error: BaseException) -> None:
        try:
            self._on_error(error)
        finally:
            self._done(self)


class _Task(QRunnable):
    def __init__(self, function: Callable[[], object], relay: _Relay) -> None:
        super().__init__()
        self._function = function
        self._relay = relay

    def run(self) -> None:
        try:
            result = self._function()
        except Exception as error:  # the single boundary that hands any failure to the GUI thread
            _logger.debug("Background task failed.", exc_info=True)
            self._relay.failed.emit(error)
        else:
            self._relay.succeeded.emit(result)


class BackgroundRunner(QObject):
    """Start ``function`` on a pool thread; ``on_success``/``on_error`` run on the GUI thread.

    Create it on the GUI thread. Results that arrive after ``dispose`` are
    dropped, so a closed window never receives callbacks. ``app.py`` waits for
    the global pool before closing backend services.
    """

    def __init__(self, pool: QThreadPool | None = None, parent: QObject | None = None) -> None:
        """Use ``pool`` (the global pool by default)."""
        super().__init__(parent)
        self._pool = pool or QThreadPool.globalInstance()
        self._relays: set[_Relay] = set()
        self._disposed = False

    @property
    def pending(self) -> int:
        """Return how many started tasks have not delivered their result yet."""
        return len(self._relays)

    def run(self, function: Callable[[], object], on_success: SuccessHandler, on_error: ErrorHandler) -> None:
        """Run ``function`` in the background."""
        relay = _Relay(self._guard(on_success), self._guard(on_error), self._relays.discard)
        self._relays.add(relay)
        self._pool.start(_Task(function, relay))

    def dispose(self) -> None:
        """Stop delivering results; tasks already running finish on their own."""
        self._disposed = True

    def _guard(self, callback: Callable[[Any], None]) -> Callable[[Any], None]:
        def deliver(value: Any) -> None:
            if not self._disposed:
                callback(value)

        return deliver
