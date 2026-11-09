"""Tests for the single-active-server application use case."""

from collections.abc import Callable

import pytest

from mcserver.application.errors import ActiveServerAlreadyExists, ServerStartFailed, ServerStopFailed
from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.domain.lifecycle import ServerState


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
