"""Polls the coordinator, because the backend has no lifecycle events yet."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.domain.lifecycle import ServerState

DEFAULT_INTERVAL_MS = 300


@dataclass(frozen=True, slots=True)
class CoordinatorSnapshot:
    """The coordinator's state and active server at one moment."""

    state: ServerState
    active_server_id: str | None


class StatusPoller(QObject):
    """Read ``state`` and ``active_server_id`` on a timer and emit ``changed`` only on change.

    This is a stand-in for backend lifecycle events: it reports what the
    coordinator says and adds no state of its own.
    """

    changed = Signal(object)  # CoordinatorSnapshot

    def __init__(
        self, coordinator: ServerCoordinator, interval_ms: int = DEFAULT_INTERVAL_MS, parent: QObject | None = None
    ) -> None:
        """Poll ``coordinator`` every ``interval_ms`` once started."""
        super().__init__(parent)
        self._coordinator = coordinator
        self._snapshot = self._read()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll_now)

    @property
    def snapshot(self) -> CoordinatorSnapshot:
        """Return the last observed snapshot."""
        return self._snapshot

    @property
    def active(self) -> bool:
        """Return whether the timer is running."""
        return self._timer.isActive()

    def start(self) -> None:
        """Begin polling."""
        self._timer.start()

    def stop(self) -> None:
        """Stop polling."""
        self._timer.stop()

    def poll_now(self) -> None:
        """Read the coordinator immediately and emit ``changed`` if anything differs."""
        snapshot = self._read()
        if snapshot != self._snapshot:
            self._snapshot = snapshot
            self.changed.emit(snapshot)

    def _read(self) -> CoordinatorSnapshot:
        return CoordinatorSnapshot(self._coordinator.state, self._coordinator.active_server_id)
