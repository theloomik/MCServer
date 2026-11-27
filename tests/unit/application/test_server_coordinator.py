"""Tests for the single-active-server coordinator: readiness, graceful stop, kill, commands (M1-BE-02/03/04/07/08)."""

import pytest

from mcserver.application.errors import (
    ActiveServerAlreadyExists,
    EulaNotAccepted,
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
from mcserver.application.ports import LaunchWarning, OutputStream, StartOptions
from mcserver.application.server_coordinator import FailureKind, ServerCoordinator
from mcserver.domain.diagnostics import FailureHint
from mcserver.domain.lifecycle import ServerLifecycle, ServerState
from tests.runtime_fakes import FakeRunner, FakeRunnerFactory, ManualScheduler, MemoryMarkers


def make(
    *, auto_ready: bool = False, stop_exits: bool = True, per_start: bool = False
) -> tuple[ServerCoordinator, FakeRunnerFactory, ManualScheduler, MemoryMarkers]:
    factory = FakeRunnerFactory(FakeRunner(auto_ready=auto_ready, stop_exits=stop_exits), per_start=per_start)
    scheduler = ManualScheduler()
    markers = MemoryMarkers()
    coordinator = ServerCoordinator(factory, scheduler=scheduler, markers=markers, startup_timeout=600, stop_timeout=90)
    return coordinator, factory, scheduler, markers


# --- start and readiness (M1-BE-02) -----------------------------------------------------------


def test_start_stays_starting_until_the_ready_line() -> None:
    coordinator, factory, scheduler, _ = make()

    report = coordinator.start_server("survival")

    assert report.server_id == "survival"
    assert coordinator.state is ServerState.STARTING
    assert coordinator.active_server_id == "survival"
    assert [delay for delay, _ in scheduler.pending] == [600]
    factory.runner.emit("[Server thread/INFO]: Preparing spawn area: 42%")
    assert coordinator.state is ServerState.STARTING

    factory.runner.ready()

    assert coordinator.state is ServerState.RUNNING
    assert scheduler.pending == []  # the startup timer was cancelled


def test_a_command_echo_never_counts_as_ready() -> None:
    coordinator, factory, _, _ = make()
    coordinator.start_server("survival")

    factory.runner.emit('Done (1.0s)! For help, type "help"', OutputStream.COMMAND)

    assert coordinator.state is ServerState.STARTING


def test_start_passes_options_and_returns_warnings() -> None:
    coordinator, factory, _, _ = make()
    factory.warnings = (LaunchWarning("java_requirement_unknown", {"version": "27.1"}),)

    report = coordinator.start_server("survival", StartOptions(allow_outdated_java=True))

    assert factory.options == [StartOptions(allow_outdated_java=True)]
    assert report.warnings == factory.warnings


@pytest.mark.parametrize(
    "error",
    [
        EulaNotAccepted("survival"),
        JavaNotFound(21),
        JavaVersionTooOld("survival", 21, 17, "java"),
        ServerWorldInUse("survival", "world"),
    ],
)
def test_preflight_errors_are_raised_unchanged_and_nothing_starts(error: Exception) -> None:
    coordinator, factory, _, markers = make()
    factory.preflight_error = error

    with pytest.raises(type(error)):
        coordinator.start_server("survival")

    assert factory.runner.started == []
    assert coordinator.state is ServerState.STOPPED
    assert coordinator.active_server_id is None
    assert markers.written == []


def test_other_factory_errors_become_start_failures() -> None:
    coordinator, factory, _, _ = make()
    factory.preflight_error = RuntimeError("configuration unreadable")

    with pytest.raises(ServerStartFailed) as error:
        coordinator.start_server("survival")

    assert error.value.server_id == "survival"
    assert coordinator.state is ServerState.STOPPED


def test_failed_start_releases_the_server_and_restores_stopped_state() -> None:
    coordinator, factory, scheduler, markers = make()
    factory.runner.start_error = RuntimeError("launcher unavailable")

    with pytest.raises(ServerStartFailed) as error:
        coordinator.start_server("survival")

    assert error.value.server_id == "survival"
    assert coordinator.active_server_id is None
    assert coordinator.state is ServerState.STOPPED
    assert scheduler.pending == []
    assert markers.markers == {}


def test_rejects_another_start_while_a_server_is_active() -> None:
    coordinator, factory, _, _ = make()
    coordinator.start_server("survival")

    with pytest.raises(ActiveServerAlreadyExists) as error:
        coordinator.start_server("creative")

    assert error.value.active_server_id == "survival"
    assert factory.runner.started == ["survival"]


def test_startup_timeout_reports_and_stops_gracefully_without_killing() -> None:
    coordinator, factory, scheduler, _ = make()
    coordinator.start_server("survival")
    factory.runner.emit("[Server thread/INFO]: Loading libraries")

    scheduler.fire_all()

    assert factory.runner.stopped == [90]
    assert factory.runner.killed == 0
    assert coordinator.state is ServerState.STOPPED
    failure = coordinator.status().last_failure
    assert failure is not None
    assert failure.kind is FailureKind.START_TIMEOUT
    assert failure.output_tail[-1] == "[Server thread/INFO]: Loading libraries"


def test_startup_timeout_whose_stop_also_times_out_stays_stopping() -> None:
    coordinator, factory, scheduler, _ = make(stop_exits=False)
    coordinator.start_server("survival")

    scheduler.fire_all()

    status = coordinator.status()
    assert status.state is ServerState.STOPPING
    assert status.stop_timed_out
    assert factory.runner.killed == 0


def test_timer_firing_after_readiness_does_nothing() -> None:
    coordinator, factory, scheduler, _ = make()
    coordinator.start_server("survival")
    pending = list(scheduler.pending)
    factory.runner.ready()

    for _delay, callback in pending:
        callback()

    assert coordinator.state is ServerState.RUNNING
    assert factory.runner.stopped == []


def test_exit_during_startup_is_recorded_with_a_diagnosis() -> None:
    coordinator, factory, _, markers = make()
    coordinator.start_server("survival")
    factory.runner.emit("[main/WARN]: You need to agree to the EULA in order to run the server.")

    factory.runner.exit(1)

    assert coordinator.state is ServerState.STOPPED
    failure = coordinator.status().last_failure
    assert failure is not None
    assert failure.kind is FailureKind.UNEXPECTED_EXIT
    assert failure.exit_code == 1
    assert failure.hint is FailureHint.EULA_NOT_ACCEPTED
    assert markers.markers == {}  # observed exit clears the marker


def test_crash_while_running_is_recorded_and_allows_another_start() -> None:
    coordinator, factory, _, _ = make(per_start=True)
    coordinator.start_server("survival")
    factory.runners["survival"].ready()

    factory.runners["survival"].exit(1)
    coordinator.start_server("creative")

    assert coordinator.take_failure("survival") is not None
    assert coordinator.take_failure("survival") is None
    assert coordinator.active_server_id == "creative"


def test_marker_is_written_with_the_process_id_while_running() -> None:
    coordinator, _, _, markers = make()

    coordinator.start_server("survival")

    assert markers.written == [("survival", 4242)]
    assert "survival" in markers.markers


# --- graceful stop and kill (M1-BE-03) --------------------------------------------------------


def test_graceful_stop_releases_the_server_and_clears_the_marker() -> None:
    coordinator, factory, _, markers = make(auto_ready=True)
    coordinator.start_server("survival")

    assert coordinator.stop_server(timeout=3.0)

    assert factory.runner.stopped == [3.0]
    assert coordinator.active_server_id is None
    assert coordinator.state is ServerState.STOPPED
    assert coordinator.status().last_failure is None
    assert markers.markers == {}


def test_stop_uses_the_default_timeout() -> None:
    coordinator, factory, _, _ = make(auto_ready=True)
    coordinator.start_server("survival")

    coordinator.stop_server()

    assert factory.runner.stopped == [90]


def test_stop_timeout_keeps_the_server_stopping_and_never_kills() -> None:
    coordinator, factory, _, markers = make(auto_ready=True, stop_exits=False)
    coordinator.start_server("survival")

    with pytest.raises(ServerStopTimedOut) as error:
        coordinator.stop_server(timeout=5)

    assert error.value.timeout == 5
    assert factory.runner.killed == 0
    status = coordinator.status()
    assert status.state is ServerState.STOPPING
    assert status.stop_timed_out
    assert status.active_server_id == "survival"
    assert "survival" in markers.markers


def test_stopping_again_after_a_timeout_only_waits() -> None:
    coordinator, factory, _, _ = make(auto_ready=True, stop_exits=False)
    coordinator.start_server("survival")
    with pytest.raises(ServerStopTimedOut):
        coordinator.stop_server(timeout=5)
    factory.runner.stop_exits = True

    assert coordinator.stop_server(timeout=7)

    assert factory.runner.stopped == [5]  # "stop" was sent only once
    assert factory.runner.waited == [7]
    assert coordinator.state is ServerState.STOPPED


def test_stop_during_startup_is_allowed() -> None:
    coordinator, factory, scheduler, _ = make()
    coordinator.start_server("survival")

    assert coordinator.stop_server()

    assert coordinator.state is ServerState.STOPPED
    assert scheduler.pending == []
    assert coordinator.status().last_failure is None


def test_kill_is_explicit_and_releases_the_server() -> None:
    coordinator, factory, _, markers = make(auto_ready=True, stop_exits=False)
    coordinator.start_server("survival")
    with pytest.raises(ServerStopTimedOut):
        coordinator.stop_server(timeout=1)

    assert coordinator.kill_server()

    assert factory.runner.killed == 1
    assert coordinator.state is ServerState.STOPPED
    assert coordinator.status().last_failure is None
    assert markers.markers == {}


def test_kill_without_active_server_is_a_no_op() -> None:
    coordinator, _, _, _ = make()

    assert not coordinator.kill_server()


def test_negative_stop_timeout_is_rejected_without_releasing_the_server() -> None:
    coordinator, factory, _, _ = make(auto_ready=True)
    coordinator.start_server("survival")

    with pytest.raises(ValueError, match="negative"):
        coordinator.stop_server(timeout=-1)

    assert factory.runner.stopped == []
    assert coordinator.state is ServerState.RUNNING


def test_failed_stop_keeps_the_server_active() -> None:
    coordinator, factory, _, _ = make(auto_ready=True)
    factory.runner.stop_error = RuntimeError("pipe broken")
    coordinator.start_server("survival")

    with pytest.raises(ServerStopFailed):
        coordinator.stop_server()

    assert coordinator.active_server_id == "survival"


def test_repeated_stop_requests_are_safe() -> None:
    coordinator, _, _, _ = make(auto_ready=True)

    assert not coordinator.stop_server()
    coordinator.start_server("survival")
    assert coordinator.stop_server()
    assert not coordinator.stop_server()


def test_stop_never_reaches_a_server_started_after_the_stopped_one_exited() -> None:
    """Regression: the runner to stop is captured together with the active server."""
    factory = FakeRunnerFactory(FakeRunner(auto_ready=True), per_start=True)
    coordinator: ServerCoordinator

    class RacingLifecycle(ServerLifecycle):
        def transition_to(self, target: ServerState) -> None:
            super().transition_to(target)
            if target is ServerState.STOPPING:
                factory.runners["survival"].exit(0)  # survival exits on its own
                coordinator.start_server("creative")  # another caller starts creative

    coordinator = ServerCoordinator(factory, RacingLifecycle(), scheduler=ManualScheduler())
    coordinator.start_server("survival")

    coordinator.stop_server(timeout=5)

    assert factory.runners["survival"].stopped == [5]
    assert factory.runners["creative"].stopped == []
    assert coordinator.active_server_id == "creative"
    assert coordinator.state is ServerState.RUNNING


# --- console commands (M1-BE-04) --------------------------------------------------------------


def test_command_reaches_the_running_server() -> None:
    coordinator, factory, _, _ = make(auto_ready=True)
    coordinator.start_server("survival")

    coordinator.send_command("survival", "  say hi ")

    assert factory.runner.commands == ["say hi"]


@pytest.mark.parametrize("command", ["", "   ", "say hi\nop me", "stop\r"])
def test_empty_or_multiline_commands_are_rejected(command: str) -> None:
    coordinator, factory, _, _ = make(auto_ready=True)
    coordinator.start_server("survival")

    with pytest.raises(InvalidServerCommand):
        coordinator.send_command("survival", command)

    assert factory.runner.commands == []


def test_commands_need_the_active_running_server() -> None:
    coordinator, factory, _, _ = make()
    with pytest.raises(ServerNotRunning):
        coordinator.send_command("survival", "say hi")
    coordinator.start_server("survival")

    with pytest.raises(ServerNotRunning):
        coordinator.send_command("survival", "say hi")  # still STARTING
    factory.runner.ready()
    with pytest.raises(ServerNotRunning):
        coordinator.send_command("creative", "say hi")


def test_broken_input_becomes_a_command_failure() -> None:
    coordinator, factory, _, _ = make(auto_ready=True)
    coordinator.start_server("survival")
    factory.runner.command_error = BrokenPipeError("closed")

    with pytest.raises(ServerCommandFailed):
        coordinator.send_command("survival", "say hi")

    assert coordinator.state is ServerState.RUNNING


def test_invalid_timeouts_are_rejected() -> None:
    with pytest.raises(ValueError):
        ServerCoordinator(FakeRunnerFactory(), startup_timeout=0)
