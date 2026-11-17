"""Use case for coordinating the single active Minecraft server (ADR 0002, 0005, 0006)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from threading import RLock, Timer

from mcserver.application.errors import (
    ActiveServerAlreadyExists,
    EulaNotAccepted,
    InvalidJavaExecutable,
    InvalidServerCommand,
    JavaNotFound,
    JavaVersionTooOld,
    ServerCommandFailed,
    ServerNotRunning,
    ServerStartFailed,
    ServerStopFailed,
    ServerStopTimedOut,
    ServerWorldInUse,
)
from mcserver.application.ports import (
    Cancel,
    LaunchWarning,
    OutputStream,
    Scheduler,
    ServerRunner,
    ServerRunnerFactory,
    SessionMarkerStore,
    StartOptions,
)
from mcserver.domain.diagnostics import FailureHint, diagnose
from mcserver.domain.lifecycle import ServerLifecycle, ServerState
from mcserver.domain.readiness import DEFAULT_READINESS_RULES, ReadinessRule, is_ready_line

_logger = logging.getLogger(__name__)

DEFAULT_STARTUP_TIMEOUT_SECONDS = 600.0
DEFAULT_STOP_TIMEOUT_SECONDS = 90.0
DIAGNOSTIC_TAIL_LINES = 40

# Failures the user can act on are raised unchanged; anything else from the factory is a start failure.
_PREFLIGHT_ERRORS = (EulaNotAccepted, InvalidJavaExecutable, JavaNotFound, JavaVersionTooOld, ServerWorldInUse)


class ThreadingScheduler:
    """Run callbacks on daemon timer threads (the production ``Scheduler``)."""

    def call_later(self, delay: float, callback: Callable[[], None]) -> Cancel:
        """Call ``callback`` after ``delay`` seconds unless the returned function is called first."""
        timer = Timer(delay, callback)
        timer.daemon = True
        timer.start()
        return timer.cancel


class FailureKind(str, Enum):
    """How a server run ended badly."""

    START_TIMEOUT = "start_timeout"
    """The server did not become ready in time; a graceful stop was started (never a kill)."""
    UNEXPECTED_EXIT = "unexpected_exit"
    """The process ended without a stop or kill request."""


@dataclass(frozen=True, slots=True)
class ServerFailure:
    """What went wrong with a server run, with the evidence needed to explain it."""

    server_id: str
    kind: FailureKind
    exit_code: int | None
    output_tail: tuple[str, ...]
    hint: FailureHint


@dataclass(frozen=True, slots=True)
class StartReport:
    """An accepted start: the server is STARTING; ``warnings`` did not block it."""

    server_id: str
    warnings: tuple[LaunchWarning, ...] = ()


@dataclass(frozen=True, slots=True)
class CoordinatorStatus:
    """Everything the GUI shows about the active server at one moment."""

    state: ServerState
    active_server_id: str | None
    stop_timed_out: bool
    """The last graceful stop did not finish in time; the process is still running (STOPPING)."""
    last_failure: ServerFailure | None


class ServerCoordinator:
    """Own the lifecycle of the single active server (ADR 0002) and its state (ADR 0005).

    * ``start_server`` checks preconditions through the runner factory, starts
      the process and stays STARTING until a readiness rule matches a console
      line. If none matches within ``startup_timeout``, a ``START_TIMEOUT``
      failure is recorded and a graceful stop begins; nothing is killed.
    * ``stop_server`` sends ``stop`` and waits; if the process has not exited
      after the timeout it raises ``ServerStopTimedOut`` and the server stays
      STOPPING. Forced termination is only ``kill_server`` (ADR 0006).
    * A process exit that nobody requested is recorded as ``UNEXPECTED_EXIT``
      with the last console lines and a diagnosis.
    * A session marker is written while a process runs and cleared whenever
      this coordinator observes its exit.
    """

    def __init__(
        self,
        runner_factory: ServerRunnerFactory,
        lifecycle: ServerLifecycle | None = None,
        *,
        scheduler: Scheduler | None = None,
        markers: SessionMarkerStore | None = None,
        startup_timeout: float = DEFAULT_STARTUP_TIMEOUT_SECONDS,
        stop_timeout: float = DEFAULT_STOP_TIMEOUT_SECONDS,
        readiness_rules: Sequence[ReadinessRule] = DEFAULT_READINESS_RULES,
    ) -> None:
        """Create a coordinator; ``scheduler`` and ``markers`` are injectable for tests."""
        if startup_timeout <= 0 or stop_timeout < 0:
            raise ValueError("Timeouts must be positive.")
        self._runner_factory = runner_factory
        self._lifecycle = lifecycle or ServerLifecycle()
        self._scheduler = scheduler or ThreadingScheduler()
        self._markers = markers
        self._startup_timeout = startup_timeout
        self._stop_timeout = stop_timeout
        self._readiness_rules = tuple(readiness_rules)
        self._lock = RLock()
        self._active_server_id: str | None = None
        self._server_runner: ServerRunner | None = None
        self._generation = 0
        self._cancel_startup_timer: Cancel | None = None
        self._stop_requested = False
        self._stop_timed_out = False
        self._last_failure: ServerFailure | None = None

    # --- queries ----------------------------------------------------------------------------

    @property
    def active_server_id(self) -> str | None:
        """Return the server currently starting, running or stopping, if any."""
        with self._lock:
            return self._active_server_id

    @property
    def state(self) -> ServerState:
        """Return the lifecycle state of the active server (STOPPED when none is active)."""
        with self._lock:
            return self._lifecycle.state

    @property
    def stop_timeout(self) -> float:
        """Return the default graceful-stop timeout in seconds."""
        return self._stop_timeout

    def configure_timeouts(self, startup_timeout: float, stop_timeout: float) -> None:
        """Use these timeouts for later starts and stops (application settings, M2-BE-06)."""
        if startup_timeout <= 0 or stop_timeout < 0:
            raise ValueError("Timeouts must be positive.")
        with self._lock:
            self._startup_timeout = startup_timeout
            self._stop_timeout = stop_timeout

    def status(self) -> CoordinatorStatus:
        """Return a consistent snapshot of state, active server, stop timeout and last failure."""
        with self._lock:
            return CoordinatorStatus(
                self._lifecycle.state, self._active_server_id, self._stop_timed_out, self._last_failure
            )

    def take_failure(self, server_id: str) -> ServerFailure | None:
        """Return and forget the last failure if it belongs to ``server_id``."""
        with self._lock:
            failure = self._last_failure
            if failure is None or failure.server_id != server_id:
                return None
            self._last_failure = None
            return failure

    # --- commands ---------------------------------------------------------------------------

    def start_server(self, server_id: str, options: StartOptions | None = None) -> StartReport:
        """Start ``server_id``; it stays STARTING until it is ready.

        Raises ``ActiveServerAlreadyExists``, the preflight errors
        (``EulaNotAccepted``, ``JavaNotFound``, ``JavaVersionTooOld``,
        ``ServerWorldInUse``) unchanged, and ``ServerStartFailed`` for anything
        else. A failed start leaves the coordinator STOPPED and reusable.
        """
        with self._lock:
            if self._active_server_id is not None:
                raise ActiveServerAlreadyExists(self._active_server_id)
            try:
                prepared = self._runner_factory.create(server_id, options or StartOptions())
            except _PREFLIGHT_ERRORS:
                raise
            except Exception as error:
                raise ServerStartFailed(server_id) from error

            self._lifecycle.transition_to(ServerState.STARTING)
            self._generation += 1
            generation = self._generation
            self._active_server_id = server_id
            self._server_runner = prepared.runner
            self._stop_requested = False
            self._stop_timed_out = False
            if self._last_failure is not None and self._last_failure.server_id == server_id:
                self._last_failure = None
            try:
                prepared.runner.start(
                    server_id,
                    lambda exit_code: self._on_process_exit(generation, server_id, exit_code),
                    lambda stream, text: self._on_output(generation, stream, text),
                )
            except Exception as error:
                self._release(generation)
                raise ServerStartFailed(server_id) from error

            self._write_marker(server_id, prepared.runner.process_id)
            if self._generation == generation and self._lifecycle.state is ServerState.STARTING:
                self._cancel_startup_timer = self._scheduler.call_later(
                    self._startup_timeout, lambda: self._on_startup_timeout(generation)
                )
            return StartReport(server_id, prepared.warnings)

    def stop_server(self, timeout: float | None = None) -> bool:
        """Stop the active server gracefully; return ``False`` when no server is active.

        Sends ``stop`` (unless a stop is already in progress, in which case it
        only waits again) and waits up to ``timeout`` seconds (default: the
        coordinator's stop timeout). Raises ``ServerStopTimedOut`` if the
        process is still running afterwards; the server stays STOPPING and
        nothing is killed. Raises ``ServerStopFailed`` if the request itself fails.
        """
        wait = self._stop_timeout if timeout is None else timeout
        if wait < 0:
            raise ValueError("Shutdown timeout must not be negative.")
        with self._lock:
            server_id = self._active_server_id
            # Capture the runner with its server: once the lock is released, the
            # process may exit and another server may be started in its place.
            runner = self._server_runner
            generation = self._generation
            if server_id is None or runner is None:
                return False
            already_stopping = self._lifecycle.state in (ServerState.STOPPING, ServerState.KILLING)
            if not already_stopping:
                self._lifecycle.transition_to(ServerState.STOPPING)
            self._cancel_timer()
            self._stop_requested = True
            self._stop_timed_out = False

        try:
            exited = runner.wait_for_exit(wait) if already_stopping else runner.stop(wait)
        except Exception as error:
            raise ServerStopFailed(server_id) from error

        if not exited:
            with self._lock:
                if self._generation == generation:
                    self._stop_timed_out = True
            raise ServerStopTimedOut(server_id, wait)
        with self._lock:
            self._release(generation)
        return True

    def kill_server(self) -> bool:
        """Terminate the active server immediately (explicit user decision); return whether one was active."""
        with self._lock:
            server_id = self._active_server_id
            runner = self._server_runner
            generation = self._generation
            if server_id is None or runner is None:
                return False
            if self._lifecycle.state is not ServerState.KILLING:
                self._lifecycle.transition_to(ServerState.KILLING)
            self._cancel_timer()
            self._stop_requested = True
        try:
            runner.kill()
        except Exception as error:
            raise ServerStopFailed(server_id) from error
        with self._lock:
            self._release(generation)
        return True

    def send_command(self, server_id: str, command: str) -> None:
        """Send one console command to ``server_id``, which must be the active, RUNNING server."""
        if "\n" in command or "\r" in command:
            raise InvalidServerCommand("A console command must be a single line.")
        if not command.strip():
            raise InvalidServerCommand("A console command must not be empty.")
        with self._lock:
            if self._active_server_id != server_id or self._lifecycle.state is not ServerState.RUNNING:
                raise ServerNotRunning(server_id)
            runner = self._server_runner
        if runner is None:
            raise ServerNotRunning(server_id)
        try:
            runner.send_command(command.strip())
        except ServerCommandFailed:
            raise
        except Exception as error:
            raise ServerCommandFailed(server_id) from error

    # --- runner events ----------------------------------------------------------------------

    def _on_output(self, generation: int, stream: OutputStream, text: str) -> None:
        """Move STARTING → RUNNING on the first ready line of the current process."""
        if stream is OutputStream.COMMAND or not is_ready_line(text, self._readiness_rules):
            return
        with self._lock:
            if self._generation == generation and self._lifecycle.state is ServerState.STARTING:
                self._lifecycle.transition_to(ServerState.RUNNING)
                self._cancel_timer()

    def _on_startup_timeout(self, generation: int) -> None:
        """Record the timeout and stop gracefully; never kill (ADR 0006)."""
        with self._lock:
            if self._generation != generation or self._lifecycle.state is not ServerState.STARTING:
                return
            runner = self._server_runner
            server_id = self._active_server_id
            if runner is None or server_id is None:
                return
            self._cancel_startup_timer = None
            self._last_failure = self._failure(server_id, FailureKind.START_TIMEOUT, None, runner)
            self._lifecycle.transition_to(ServerState.STOPPING)
            self._stop_requested = True
        try:
            exited = runner.stop(self._stop_timeout)
        except Exception:
            _logger.exception("Graceful stop after the startup timeout failed for %r.", server_id)
            exited = False
        with self._lock:
            if self._generation != generation:
                return
            if exited:
                self._release(generation)
            else:
                self._stop_timed_out = True

    def _on_process_exit(self, generation: int, server_id: str, exit_code: int) -> None:
        """Release the reservation; an exit nobody requested is recorded as a failure."""
        with self._lock:
            if self._generation != generation or self._active_server_id != server_id:
                if self._active_server_id != server_id:
                    self._clear_marker(server_id)
                return
            runner = self._server_runner
            if not self._stop_requested and runner is not None:
                self._last_failure = self._failure(server_id, FailureKind.UNEXPECTED_EXIT, exit_code, runner)
            self._release(generation)

    # --- helpers ------------------------------------------------------------------------------

    @staticmethod
    def _failure(server_id: str, kind: FailureKind, exit_code: int | None, runner: ServerRunner) -> ServerFailure:
        try:
            tail = tuple(runner.output_tail(DIAGNOSTIC_TAIL_LINES))
        except Exception:
            _logger.exception("Could not read the output tail of %r.", server_id)
            tail = ()
        return ServerFailure(server_id, kind, exit_code, tail, diagnose(tail))

    def _release(self, generation: int) -> None:
        """Return to STOPPED and clear the active server, if ``generation`` is still current."""
        if self._generation != generation or self._active_server_id is None:
            return
        server_id = self._active_server_id
        self._cancel_timer()
        if self._lifecycle.state is not ServerState.STOPPED:
            self._lifecycle.transition_to(ServerState.STOPPED)
        self._active_server_id = None
        self._server_runner = None
        self._stop_requested = False
        self._stop_timed_out = False
        self._clear_marker(server_id)

    def _cancel_timer(self) -> None:
        cancel, self._cancel_startup_timer = self._cancel_startup_timer, None
        if cancel is not None:
            cancel()

    def _write_marker(self, server_id: str, process_id: int | None) -> None:
        if self._markers is None:
            return
        try:
            self._markers.write(server_id, process_id)
        except Exception:
            _logger.exception("Could not write the session marker for %r.", server_id)

    def _clear_marker(self, server_id: str) -> None:
        if self._markers is None:
            return
        try:
            self._markers.clear(server_id)
        except Exception:
            _logger.exception("Could not clear the session marker for %r.", server_id)
