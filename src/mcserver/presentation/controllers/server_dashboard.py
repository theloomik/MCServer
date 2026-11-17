"""Start/stop/kill controls, console commands and live status for the selected server."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, Signal

from mcserver.application.errors import EulaNotAccepted, JavaNotFound, JavaVersionTooOld, ServerStopTimedOut
from mcserver.application.ports import StartOptions
from mcserver.application.server_coordinator import ServerCoordinator, ServerFailure, StartReport
from mcserver.presentation.adapters.status_poller import CoordinatorSnapshot, StatusPoller
from mcserver.presentation.controllers.server_list import ServerRow, ServerStatus, status_for
from mcserver.presentation.errors import UserMessage, describe_error, describe_failure
from mcserver.presentation.workers import BackgroundRunner

_logger = logging.getLogger(__name__)


class Operation(Enum):
    """A start, stop or kill request that is still running in the background."""

    STARTING = "starting"
    STOPPING = "stopping"
    KILLING = "killing"


@dataclass(frozen=True, slots=True)
class DashboardState:
    """What the dashboard shows for the selected server."""

    row: ServerRow | None = None
    status: ServerStatus = ServerStatus.UNKNOWN
    java_available: bool = False
    operation: Operation | None = None
    other_active_server: str | None = None
    """Another server that is active, which prevents starting this one (single active server)."""
    stop_timed_out: bool = False
    """This server's graceful stop did not finish in time; it is still running (STOPPING)."""
    error: UserMessage | None = None
    notice: UserMessage | None = None
    success: UserMessage | None = None
    """A confirmation such as "server created"; cleared when the server is started."""

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
        """Return whether Stop should be enabled (after a stop timeout it waits again)."""
        if self.row is None or not self.java_available or self.operation is not None:
            return False
        if self.status in (ServerStatus.RUNNING, ServerStatus.STARTING):
            return True
        return self.status is ServerStatus.STOPPING and self.stop_timed_out

    @property
    def can_kill(self) -> bool:
        """Return whether Kill is offered: only while the server is stopping (ADR 0006)."""
        return (
            self.row is not None
            and self.java_available
            and self.operation is not Operation.KILLING
            and self.status is ServerStatus.STOPPING
        )

    @property
    def can_send_command(self) -> bool:
        """Return whether console commands can be sent."""
        return self.row is not None and self.status is ServerStatus.RUNNING


class ServerDashboardController(QObject):
    """Drive ``ServerCoordinator`` for the selected server and publish ``DashboardState``.

    Start, stop, kill and commands run in the background; the status always
    comes from the coordinator (via ``StatusPoller``), never from the GUI's own
    bookkeeping. Failed runs are reported with the coordinator's diagnosis.
    """

    state_changed = Signal(object)  # DashboardState
    operation_finished = Signal()
    eula_required = Signal(str)  # server_id
    java_problem = Signal(object)  # JavaNotFound | JavaVersionTooOld
    stop_timed_out = Signal(str)  # server_id

    def __init__(
        self,
        coordinator: ServerCoordinator | None,
        poller: StatusPoller | None,
        runner: BackgroundRunner,
        parent: QObject | None = None,
    ) -> None:
        """Control ``coordinator``; both it and ``poller`` may be ``None`` (no backend in some tests)."""
        super().__init__(parent)
        self._coordinator = coordinator
        self._poller = poller
        self._runner = runner
        self._row: ServerRow | None = None
        self._operation: Operation | None = None
        self._pending = 0
        self._errors: dict[str, UserMessage] = {}
        self._notices: dict[str, UserMessage] = {}
        self._successes: dict[str, UserMessage] = {}
        self._stop_requested: set[str] = set()
        self._seen_failure: ServerFailure | None = None
        self._state = DashboardState()
        if poller is not None:
            self._last_snapshot: CoordinatorSnapshot | None = poller.snapshot
            self._seen_failure = poller.snapshot.last_failure
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
        """Return whether a start, stop or kill is in progress."""
        return self._operation is not None

    @property
    def active_server_id(self) -> str | None:
        """Return the coordinator's active server right now (not the last polled value)."""
        return self._coordinator.active_server_id if self._coordinator is not None else None

    @property
    def stop_timeout(self) -> float:
        """Return the graceful-stop timeout in seconds."""
        return self._coordinator.stop_timeout if self._coordinator is not None else 0.0

    def show_server(self, row: ServerRow | None) -> None:
        """Switch the dashboard to ``row`` (or the welcome page for ``None``)."""
        self._row = row
        self._publish()

    def report_created(self, server_id: str) -> None:
        """Confirm on the dashboard that ``server_id`` was just created."""
        self._successes[server_id] = UserMessage("dashboard.success.created", {"server_id": server_id})
        self._publish()

    def start(self, options: StartOptions | None = None) -> None:
        """Start the selected server in the background."""
        if not self._state.can_start or self._coordinator is None or self._row is None:
            return
        server_id = self._row.server_id
        coordinator = self._coordinator
        self._errors.pop(server_id, None)
        self._notices.pop(server_id, None)
        self._successes.pop(server_id, None)
        self._stop_requested.discard(server_id)
        self._begin(Operation.STARTING)
        self._runner.run(
            lambda: coordinator.start_server(server_id, options),
            lambda report: self._started(server_id, report),
            lambda error: self._start_failed(server_id, error),
        )

    def stop(self) -> None:
        """Stop the selected (active) server gracefully in the background."""
        if not self._state.can_stop or self._coordinator is None or self._row is None:
            return
        self.stop_active(self._row.server_id)

    def stop_active(self, server_id: str | None = None) -> bool:
        """Stop whichever server is active (also used on exit); return whether a stop was started."""
        target = server_id or self.active_server_id
        if self._coordinator is None or target is None or self._operation is not None:
            return False
        coordinator = self._coordinator
        self._errors.pop(target, None)
        self._stop_requested.add(target)
        self._begin(Operation.STOPPING)
        self._runner.run(
            coordinator.stop_server,
            lambda _result: self._finish(),
            lambda error: self._stop_failed(target, error),
        )
        return True

    def kill(self) -> bool:
        """Kill the active server immediately (the caller has asked the user); return whether it was started."""
        target = self.active_server_id
        if self._coordinator is None or target is None or self._operation is Operation.KILLING:
            return False
        coordinator = self._coordinator
        self._stop_requested.add(target)
        self._begin(Operation.KILLING)
        self._runner.run(
            coordinator.kill_server,
            lambda _result: self._finish(),
            lambda error: self._fail(target, error),
        )
        return True

    def send_command(self, command: str) -> None:
        """Send a console command to the selected server in the background."""
        if self._coordinator is None or self._row is None or not command.strip():
            return
        server_id = self._row.server_id
        coordinator = self._coordinator
        self._notices.pop(server_id, None)
        self._runner.run(
            lambda: coordinator.send_command(server_id, command),
            lambda _result: None,
            lambda error: self._command_failed(server_id, error),
        )

    # --- results --------------------------------------------------------------------------

    def _begin(self, operation: Operation) -> None:
        self._operation = operation
        self._pending += 1
        self._publish()

    def _started(self, server_id: str, report: StartReport | None) -> None:
        """A start was accepted (STARTING); warnings and an immediate exit are reported."""
        if report is not None and report.warnings:
            warning = report.warnings[0]
            self._notices[server_id] = UserMessage(f"dashboard.warning.{warning.code}", dict(warning.params))
        if self._poller is not None:
            self._poller.poll_now()
        snapshot = self._last_snapshot
        if (
            snapshot is not None
            and snapshot.active_server_id != server_id
            and server_id not in self._stop_requested
            and server_id not in self._errors
        ):
            self._notices[server_id] = UserMessage("dashboard.notice.stopped_unexpectedly", {"server_id": server_id})
        self._finish()

    def _start_failed(self, server_id: str, error: BaseException) -> None:
        if isinstance(error, EulaNotAccepted):
            self._finish()
            self.eula_required.emit(server_id)
            return
        if isinstance(error, (JavaNotFound, JavaVersionTooOld)):
            self._errors[server_id] = describe_error(error)
            self._finish()
            self.java_problem.emit(error)
            return
        self._fail(server_id, error)

    def _stop_failed(self, server_id: str, error: BaseException) -> None:
        self._fail(server_id, error)
        if isinstance(error, ServerStopTimedOut):
            self.stop_timed_out.emit(server_id)

    def _command_failed(self, server_id: str, error: BaseException) -> None:
        message = describe_error(error)
        self._notices[server_id] = UserMessage(
            "dashboard.notice.command_failed", {"reason_key": message.key, **message.params}, message.details
        )
        self._publish()

    def _finish(self) -> None:
        self._pending = max(0, self._pending - 1)
        if self._pending == 0:
            self._operation = None
        if self._poller is not None:
            self._poller.poll_now()
        self._publish()
        if self._pending == 0:
            self.operation_finished.emit()

    def _fail(self, server_id: str, error: BaseException) -> None:
        _logger.error("Server operation for %r failed:\n%s", server_id, describe_error(error).details)
        self._errors[server_id] = describe_error(error)
        self._finish()

    def _on_snapshot(self, snapshot: CoordinatorSnapshot) -> None:
        previous = self._last_snapshot
        self._last_snapshot = snapshot
        failure = snapshot.last_failure
        if failure is not None and failure is not self._seen_failure:
            self._seen_failure = failure
            self._errors[failure.server_id] = describe_failure(failure)
            self._notices.pop(failure.server_id, None)
        stopped = previous.active_server_id if previous else None
        if stopped is not None and snapshot.active_server_id != stopped:
            if stopped in self._stop_requested:
                self._stop_requested.discard(stopped)
            elif stopped not in self._errors:
                self._notices[stopped] = UserMessage("dashboard.notice.stopped_unexpectedly", {"server_id": stopped})
        self._publish()

    def _publish(self) -> None:
        row = self._row
        snapshot = self._last_snapshot
        java_available = self._coordinator is not None
        stop_timed_out = False
        if row is None or snapshot is None:
            status = ServerStatus.UNKNOWN
            other_active = None
        else:
            status = status_for(row.server_id, snapshot.state, snapshot.active_server_id)
            active = snapshot.active_server_id
            other_active = active if active is not None and active != row.server_id else None
            stop_timed_out = snapshot.stop_timed_out and active == row.server_id
        self._state = DashboardState(
            row=row,
            status=status,
            java_available=java_available,
            operation=self._operation,
            other_active_server=other_active,
            stop_timed_out=stop_timed_out,
            error=self._errors.get(row.server_id) if row else None,
            notice=self._notices.get(row.server_id) if row else None,
            success=self._successes.get(row.server_id) if row else None,
        )
        self.state_changed.emit(self._state)
