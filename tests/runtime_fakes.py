"""In-memory stand-ins for the server runtime ports (no processes, no threads, no waiting)."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event

from mcserver.application.errors import ServerCommandFailed
from mcserver.application.ports import (
    LaunchWarning,
    OutputStream,
    PreparedLaunch,
    ProcessOutputHandler,
    SessionMarker,
    StartOptions,
)

READY_LINE = '[12:00:00] [Server thread/INFO]: Done (3.210s)! For help, type "help"'


class FakeRunner:
    """``ServerRunner`` fake. By default it becomes ready during ``start`` and exits on ``stop``."""

    def __init__(self, *, auto_ready: bool = True, stop_exits: bool = True) -> None:
        self.auto_ready = auto_ready
        self.stop_exits = stop_exits
        self.on_exit: Callable[[int], None] | None = None
        self.on_output: ProcessOutputHandler | None = None
        self.start_gate: Event | None = None
        self.start_error: Exception | None = None
        self.stop_error: Exception | None = None
        self.command_error: Exception | None = None
        self.crash_on_start = False
        self.started: list[str] = []
        self.stopped: list[float] = []
        self.waited: list[float] = []
        self.commands: list[str] = []
        self.killed = 0
        self.lines: list[str] = []
        self.process_id: int | None = None

    def start(
        self, server_id: str, on_exit: Callable[[int], None], on_output: ProcessOutputHandler | None = None
    ) -> None:
        self.started.append(server_id)
        if self.start_gate is not None:
            self.start_gate.wait(5)
        if self.start_error is not None:
            raise self.start_error
        self.on_exit = on_exit
        self.on_output = on_output
        self.process_id = 4242
        if self.crash_on_start:
            self.emit("Error: Unable to access jarfile server.jar")
            self.exit(1)  # the process dies before anyone could poll it
        elif self.auto_ready:
            self.emit(READY_LINE)

    def emit(self, line: str, stream: OutputStream = OutputStream.STDOUT) -> None:
        """Simulate one console line."""
        self.lines.append(line)
        if self.on_output is not None:
            self.on_output(stream, line)

    def ready(self) -> None:
        """Simulate Minecraft finishing its startup."""
        self.emit(READY_LINE)

    def send_command(self, command: str) -> None:
        if self.command_error is not None:
            raise self.command_error
        if self.on_exit is None:
            raise ServerCommandFailed("?")
        self.commands.append(command)

    def stop(self, timeout: float) -> bool:
        self.stopped.append(timeout)
        if self.stop_error is not None:
            raise self.stop_error
        if self.stop_exits:
            self.exit(0)
            return True
        return False

    def wait_for_exit(self, timeout: float) -> bool:
        self.waited.append(timeout)
        if self.stop_exits:
            self.exit(0)
            return True
        return self.on_exit is None

    def kill(self) -> None:
        self.killed += 1
        self.exit(137)

    def output_tail(self, limit: int = 40) -> tuple[str, ...]:
        return tuple(self.lines[-limit:])

    def exit(self, code: int) -> None:
        """Simulate the process ending (normally or by crashing)."""
        on_exit, self.on_exit = self.on_exit, None
        if on_exit is not None:
            on_exit(code)


class FakeRunnerFactory:
    """Return one shared runner (or a new one per start) after optional preflight failures."""

    def __init__(self, runner: FakeRunner | None = None, *, per_start: bool = False) -> None:
        self.runner = runner or FakeRunner()
        self.per_start = per_start
        self.runners: dict[str, FakeRunner] = {}
        self.preflight_error: Exception | None = None
        self.warnings: tuple[LaunchWarning, ...] = ()
        self.options: list[StartOptions] = []
        self.created: list[str] = []

    def create(self, server_id: str, options: StartOptions) -> PreparedLaunch:
        self.created.append(server_id)
        self.options.append(options)
        if self.preflight_error is not None:
            raise self.preflight_error
        runner = FakeRunner(auto_ready=self.runner.auto_ready) if self.per_start else self.runner
        self.runners[server_id] = runner
        return PreparedLaunch(runner, self.warnings)


class ManualScheduler:
    """``Scheduler`` whose callbacks run only when the test fires them."""

    def __init__(self) -> None:
        self.pending: list[tuple[float, Callable[[], None]]] = []
        self.cancelled = 0

    def call_later(self, delay: float, callback: Callable[[], None]) -> Callable[[], None]:
        entry = (delay, callback)
        self.pending.append(entry)

        def cancel() -> None:
            if entry in self.pending:
                self.pending.remove(entry)
                self.cancelled += 1

        return cancel

    def fire_all(self) -> None:
        """Run every pending callback as if its delay had passed."""
        entries, self.pending = self.pending, []
        for _delay, callback in entries:
            callback()


class MemoryMarkers:
    """``SessionMarkerStore`` fake."""

    def __init__(self, *leftover: str) -> None:
        self.markers: dict[str, str] = {server_id: "2026-11-14T10:00:00+00:00" for server_id in leftover}
        self.written: list[tuple[str, int | None]] = []

    def write(self, server_id: str, process_id: int | None) -> None:
        self.written.append((server_id, process_id))
        self.markers[server_id] = "2026-11-15T09:00:00+00:00"

    def clear(self, server_id: str) -> None:
        self.markers.pop(server_id, None)

    def leftovers(self) -> tuple[SessionMarker, ...]:
        return tuple(SessionMarker(server_id, started) for server_id, started in self.markers.items())
