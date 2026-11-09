"""Tests for the single-active-server application use case."""

from collections.abc import Callable

import pytest

from mcserver.application.errors import ActiveServerAlreadyExists, ServerStartFailed, ServerStopFailed
from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.domain.lifecycle import ServerLifecycle, ServerState


class FakeServerRunner:
    """Record runner interactions without launching a Minecraft process."""

    def __init__(self, start_failure: Exception | None = None, stop_failure: Exception | None = None) -> None:
        self.start_failure = start_failure
        self.stop_failure = stop_failure
        self.started_server_ids: list[str] = []
        self.stop_timeouts: list[float] = []
        self._on_exit: Callable[[int], None] | None = None

    def start(self, server_id: str, on_exit: Callable[[int], None]) -> None:
        self.started_server_ids.append(server_id)
        if self.start_failure is not None:
            raise self.start_failure
        self._on_exit = on_exit

    def stop(self, timeout: float) -> None:
        self.stop_timeouts.append(timeout)
        if self.stop_failure is not None:
            raise self.stop_failure
        self.emit_exit(0)

    def emit_exit(self, exit_code: int) -> None:
        """Simulate an asynchronous process exit notification."""
        if self._on_exit is not None:
            self._on_exit(exit_code)


class FakeServerRunnerFactory:
    """Return deterministic fake runners by server identifier."""

    def __init__(self, runner: FakeServerRunner) -> None:
        self.runner = runner
        self.created_server_ids: list[str] = []

    def create(self, server_id: str) -> FakeServerRunner:
        self.created_server_ids.append(server_id)
        return self.runner


class PerServerFactory:
    """Create a separate fake runner for every start, keyed by server identifier."""

    def __init__(self) -> None:
        self.runners: dict[str, FakeServerRunner] = {}

    def create(self, server_id: str) -> FakeServerRunner:
        runner = FakeServerRunner()
        self.runners[server_id] = runner
        return runner


def test_stop_never_reaches_a_server_started_after_the_stopped_one_exited() -> None:
    """Regression: the runner to stop is captured together with the active server.

    The lifecycle hook simulates the race where, right after ``stop_server``
    reads the active server, its process exits and another caller starts a
    different server before ``runner.stop`` is called.
    """
    factory = PerServerFactory()
    coordinator: ServerCoordinator

    class RacingLifecycle(ServerLifecycle):
        def transition_to(self, target: ServerState) -> None:
            super().transition_to(target)
            if target is ServerState.STOPPING:
                factory.runners["survival"].emit_exit(0)  # survival exits on its own
                coordinator.start_server("creative")  # another caller starts creative

    coordinator = ServerCoordinator(factory, RacingLifecycle())
    coordinator.start_server("survival")

    coordinator.stop_server(timeout=5)

    assert factory.runners["survival"].stop_timeouts == [5]
    assert factory.runners["creative"].stop_timeouts == []
    assert coordinator.active_server_id == "creative"
    assert coordinator.state is ServerState.RUNNING


def test_negative_stop_timeout_is_rejected_without_releasing_the_server() -> None:
    """Regression: an invalid timeout must not mark a still-running server as stopped."""
    runner = FakeServerRunner()
    coordinator = ServerCoordinator(FakeServerRunnerFactory(runner))
    coordinator.start_server("survival")

    with pytest.raises(ValueError, match="negative"):
        coordinator.stop_server(timeout=-1)

    assert runner.stop_timeouts == []
    assert coordinator.active_server_id == "survival"
    assert coordinator.state is ServerState.RUNNING


def test_starts_selected_server_and_marks_it_running() -> None:
    runner = FakeServerRunner()
    coordinator = ServerCoordinator(FakeServerRunnerFactory(runner))

    coordinator.start_server("survival")

    assert runner.started_server_ids == ["survival"]
    assert coordinator.active_server_id == "survival"
    assert coordinator.state is ServerState.RUNNING


def test_rejects_another_start_while_a_server_is_active() -> None:
    runner = FakeServerRunner()
    coordinator = ServerCoordinator(FakeServerRunnerFactory(runner))
    coordinator.start_server("survival")

    with pytest.raises(ActiveServerAlreadyExists) as error:
        coordinator.start_server("creative")

    assert error.value.active_server_id == "survival"
    assert runner.started_server_ids == ["survival"]
    assert coordinator.active_server_id == "survival"
    assert coordinator.state is ServerState.RUNNING


def test_failed_start_releases_the_server_and_restores_stopped_state() -> None:
    runner = FakeServerRunner(start_failure=RuntimeError("launcher unavailable"))
    coordinator = ServerCoordinator(FakeServerRunnerFactory(runner))

    with pytest.raises(ServerStartFailed) as error:
        coordinator.start_server("survival")

    assert error.value.server_id == "survival"
    assert runner.started_server_ids == ["survival"]
    assert coordinator.active_server_id is None
    assert coordinator.state is ServerState.STOPPED


def test_process_exit_releases_reservation_and_allows_another_start() -> None:
    runner = FakeServerRunner()
    coordinator = ServerCoordinator(FakeServerRunnerFactory(runner))
    coordinator.start_server("survival")

    runner.emit_exit(1)
    coordinator.start_server("creative")

    assert runner.started_server_ids == ["survival", "creative"]
    assert coordinator.active_server_id == "creative"
    assert coordinator.state is ServerState.RUNNING


def test_graceful_stop_releases_the_server() -> None:
    runner = FakeServerRunner()
    coordinator = ServerCoordinator(FakeServerRunnerFactory(runner))
    coordinator.start_server("survival")

    assert coordinator.stop_server(timeout=3.0)

    assert runner.stop_timeouts == [3.0]
    assert coordinator.active_server_id is None
    assert coordinator.state is ServerState.STOPPED


def test_repeated_stop_requests_are_safe() -> None:
    runner = FakeServerRunner()
    coordinator = ServerCoordinator(FakeServerRunnerFactory(runner))

    assert not coordinator.stop_server()
    coordinator.start_server("survival")
    assert coordinator.stop_server()
    assert not coordinator.stop_server()


def test_failed_stop_releases_the_server() -> None:
    runner = FakeServerRunner(stop_failure=RuntimeError("shutdown failed"))
    coordinator = ServerCoordinator(FakeServerRunnerFactory(runner))
    coordinator.start_server("survival")

    with pytest.raises(ServerStopFailed) as error:
        coordinator.stop_server()

    assert error.value.server_id == "survival"
    assert coordinator.active_server_id is None
    assert coordinator.state is ServerState.STOPPED
