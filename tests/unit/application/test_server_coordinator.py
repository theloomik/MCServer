"""Tests for the single-active-server application use case."""

import pytest

from mcserver.application.errors import ActiveServerAlreadyExists, ServerStartFailed
from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.domain.lifecycle import ServerState


class FakeServerStarter:
    """Record start requests without launching a Minecraft process."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.started_server_ids: list[str] = []

    def start(self, server_id: str) -> None:
        self.started_server_ids.append(server_id)
        if self.failure is not None:
            raise self.failure


def test_starts_selected_server_and_marks_it_as_starting() -> None:
    starter = FakeServerStarter()
    coordinator = ServerCoordinator(starter)

    coordinator.start_server("survival")

    assert starter.started_server_ids == ["survival"]
    assert coordinator.active_server_id == "survival"
    assert coordinator.state is ServerState.STARTING


def test_rejects_another_start_while_a_server_is_starting() -> None:
    starter = FakeServerStarter()
    coordinator = ServerCoordinator(starter)
    coordinator.start_server("survival")

    with pytest.raises(ActiveServerAlreadyExists) as error:
        coordinator.start_server("creative")

    assert error.value.active_server_id == "survival"
    assert starter.started_server_ids == ["survival"]
    assert coordinator.active_server_id == "survival"
    assert coordinator.state is ServerState.STARTING


def test_failed_start_releases_the_server_and_restores_stopped_state() -> None:
    starter = FakeServerStarter(failure=RuntimeError("launcher unavailable"))
    coordinator = ServerCoordinator(starter)

    with pytest.raises(ServerStartFailed) as error:
        coordinator.start_server("survival")

    assert error.value.server_id == "survival"
    assert starter.started_server_ids == ["survival"]
    assert coordinator.active_server_id is None
    assert coordinator.state is ServerState.STOPPED


def test_can_start_another_server_after_a_failed_start() -> None:
    starter = FakeServerStarter(failure=RuntimeError("launcher unavailable"))
    coordinator = ServerCoordinator(starter)

    with pytest.raises(ServerStartFailed):
        coordinator.start_server("survival")

    starter.failure = None
    coordinator.start_server("creative")

    assert starter.started_server_ids == ["survival", "creative"]
    assert coordinator.active_server_id == "creative"
    assert coordinator.state is ServerState.STARTING
