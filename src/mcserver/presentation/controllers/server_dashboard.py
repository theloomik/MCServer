"""Start/stop controls and live status for the selected server."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, Signal

from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.presentation.adapters.status_poller import CoordinatorSnapshot, StatusPoller
from mcserver.presentation.controllers.server_list import ServerRow, ServerStatus, status_for
from mcserver.presentation.errors import UserMessage, describe_error
from mcserver.presentation.workers import BackgroundRunner

_logger = logging.getLogger(__name__)

STOP_TIMEOUT_SECONDS = 10.0


class Operation(Enum):
    """A start or stop request that is still running in the background."""

    STARTING = "starting"
    STOPPING = "stopping"


@dataclass(frozen=True, slots=True)
class DashboardState:
    """What the dashboard shows for the selected server."""

    row: ServerRow | None = None
    status: ServerStatus = ServerStatus.UNKNOWN
    java_available: bool = False
    operation: Operation | None = None
    other_active_server: str | None = None
    """Another server that is active, which prevents starting this one (single active server)."""
    error: UserMessage | None = None
    notice: UserMessage | None = None

    @property
    def can_start(self) -> bool:
        """Return whether Start should be enabled."""
        return (
            self.row is not None
            and self.java_available
            and self.operation is None
            and self.other_active_server is None
            and self.status is ServerStatus.STOPPED
        )

    @property
    def can_stop(self) -> bool:
        """Return whether Stop should be enabled."""
        return (
            self.row is not None
            and self.java_available
            and self.operation is None
            and self.status in (ServerStatus.RUNNING, ServerStatus.STARTING)
        )


class ServerDashboardController(QObject):
    """Drive ``ServerCoordinator`` for the selected server and publish ``DashboardState``.

    Start and stop run in the background; the status always comes from the
    coordinator (via ``StatusPoller``), never from the GUI's own bookkeeping.
    A server that stops without a stop request from this window is reported
    as stopped unexpectedly, because the backend exposes no exit code.
    """

    state_changed = Signal(object)  # DashboardState
    operation_finished = Signal()

    def __init__(
        self,
        coordinator: ServerCoordinator | None,
        poller: StatusPoller | None,
        runner: BackgroundRunner,
        parent: QObject | None = None,
    ) -> None:
        """Control ``coordinator``; both it and ``poller`` are ``None`` when Java is missing."""
        super().__init__(parent)
        self._coordinator = coordinator
        self._poller = poller
        self._runner = runner
        self._row: ServerRow | None = None
        self._operation: Operation | None = None
        self._errors: dict[str, UserMessage] = {}
        self._notices: dict[str, UserMessage] = {}
        self._stop_requested: set[str] = set()
        self._state = DashboardState()
        if poller is not None:
            self._last_snapshot: CoordinatorSnapshot | None = poller.snapshot
            poller.changed.connect(self._on_snapshot)
        else:
            self._last_snapshot = None
        self._publish()

    @property
    def state(self) -> DashboardState:
        """Return the latest dashboard state."""
        return self._state

    @property
    def busy(self) -> bool:
        """Return whether a start or stop is in progress."""
        return self._operation is not None

    @property
    def active_server_id(self) -> str | None:
        """Return the coordinator's active server right now (not the last polled value)."""
        return self._coordinator.active_server_id if self._coordinator is not None else None

    def show_server(self, row: ServerRow | None) -> None:
        """Switch the dashboard to ``row`` (or the welcome page for ``None``)."""
        self._row = row
        self._publish()

    def start(self) -> None:
        """Start the selected server in the background."""
        if not self._state.can_start or self._coordinator is None or self._row is None:
            return
        server_id = self._row.server_id
        coordinator = self._coordinator
        self._errors.pop(server_id, None)
        self._notices.pop(server_id, None)
        self._stop_requested.discard(server_id)
        self._begin(Operation.STARTING)
        self._runner.run(
            lambda: coordinator.start_server(server_id),
            lambda _result: self._started(server_id),
            lambda error: self._fail(server_id, error),
        )

    def stop(self) -> None:
        """Stop the active server in the background."""
        if not self._state.can_stop or self._coordinator is None or self._row is None:
            return
        server_id = self._row.server_id
        self.stop_active(server_id)

    def stop_active(self, server_id: str | None = None) -> bool:
        """Stop whichever server is active (used on exit); return whether a stop was started."""
        target = server_id or self.active_server_id
        if self._coordinator is None or target is None or self._operation is not None:
            return False
        coordinator = self._coordinator
        self._errors.pop(target, None)
        self._stop_requested.add(target)
        self._begin(Operation.STOPPING)
        self._runner.run(
            lambda: coordinator.stop_server(STOP_TIMEOUT_SECONDS),
            lambda _result: self._finish(),
            lambda error: self._fail(target, error),
        )
        return True

    def _begin(self, operation: Operation) -> None:
        self._operation = operation
        self._publish()

    def _started(self, server_id: str) -> None:
        """A start was accepted; a process that already died before the first poll is reported too."""
        if self._poller is not None:
            self._poller.poll_now()
        snapshot = self._last_snapshot
        if snapshot is not None and snapshot.active_server_id != server_id and server_id not in self._stop_requested:
            self._notices[server_id] = UserMessage("dashboard.notice.stopped_unexpectedly", {"server_id": server_id})
        self._finish()

    def _finish(self) -> None:
        self._operation = None
        if self._poller is not None:
            self._poller.poll_now()
        self._publish()
        self.operation_finished.emit()

    def _fail(self, server_id: str, error: BaseException) -> None:
        _logger.error("Server operation for %r failed:\n%s", server_id, describe_error(error).details)
        self._errors[server_id] = describe_error(error)
        self._finish()

    def _on_snapshot(self, snapshot: CoordinatorSnapshot) -> None:
        previous = self._last_snapshot
        self._last_snapshot = snapshot
        stopped = previous.active_server_id if previous else None
        if stopped is not None and snapshot.active_server_id != stopped:
            if stopped in self._stop_requested:
                self._stop_requested.discard(stopped)
            else:
                self._notices[stopped] = UserMessage("dashboard.notice.stopped_unexpectedly", {"server_id": stopped})
        self._publish()

    def _publish(self) -> None:
        row = self._row
        snapshot = self._last_snapshot
        java_available = self._coordinator is not None
        if row is None:
            status = ServerStatus.UNKNOWN
            other_active = None
        elif snapshot is None:
            status = ServerStatus.UNKNOWN
            other_active = None
        else:
            status = status_for(row.server_id, snapshot.state, snapshot.active_server_id)
            active = snapshot.active_server_id
            other_active = active if active is not None and active != row.server_id else None
        self._state = DashboardState(
            row=row,
            status=status,
            java_available=java_available,
            operation=self._operation,
            other_active_server=other_active,
            error=self._errors.get(row.server_id) if row else None,
            notice=self._notices.get(row.server_id) if row else None,
        )
        self.state_changed.emit(self._state)
