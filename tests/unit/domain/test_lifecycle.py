"""Tests for the framework-independent server lifecycle domain model."""

import pytest

from mcserver.domain.errors import InvalidStateTransition
from mcserver.domain.lifecycle import ServerLifecycle, ServerState

ALLOWED_TRANSITIONS = {
    (ServerState.STOPPED, ServerState.STARTING),
    (ServerState.STARTING, ServerState.RUNNING),
    (ServerState.STARTING, ServerState.STOPPED),
    (ServerState.STARTING, ServerState.KILLING),
    (ServerState.RUNNING, ServerState.STOPPING),
    (ServerState.RUNNING, ServerState.STOPPED),
    (ServerState.RUNNING, ServerState.KILLING),
    (ServerState.STOPPING, ServerState.STOPPED),
    (ServerState.STOPPING, ServerState.KILLING),
    (ServerState.KILLING, ServerState.STOPPED),
}


def lifecycle_in(state: ServerState) -> ServerLifecycle:
    """Build a lifecycle in a reachable state without bypassing its public API."""
    lifecycle = ServerLifecycle()
    paths = {
        ServerState.STOPPED: (),
        ServerState.STARTING: (ServerState.STARTING,),
        ServerState.RUNNING: (ServerState.STARTING, ServerState.RUNNING),
        ServerState.STOPPING: (ServerState.STARTING, ServerState.RUNNING, ServerState.STOPPING),
        ServerState.KILLING: (ServerState.STARTING, ServerState.KILLING),
    }
    for target in paths[state]:
        lifecycle.transition_to(target)
    return lifecycle


@pytest.mark.parametrize(
    ("source", "target"), sorted(ALLOWED_TRANSITIONS, key=lambda pair: (pair[0].name, pair[1].name))
)
def test_all_allowed_transitions(source: ServerState, target: ServerState) -> None:
    lifecycle = lifecycle_in(source)

    assert lifecycle.can_transition_to(target)
    lifecycle.transition_to(target)

    assert lifecycle.state is target


def test_initial_state_is_stopped() -> None:
    assert ServerLifecycle().state is ServerState.STOPPED


@pytest.mark.parametrize("source", list(ServerState))
@pytest.mark.parametrize("target", list(ServerState))
def test_all_disallowed_transitions_raise_and_preserve_state(source: ServerState, target: ServerState) -> None:
    if (source, target) in ALLOWED_TRANSITIONS:
        pytest.skip("Allowed transitions are covered separately.")

    lifecycle = lifecycle_in(source)

    with pytest.raises(InvalidStateTransition, match=rf"{source.name}.*{target.name}"):
        lifecycle.transition_to(target)

    assert lifecycle.state is source


def test_can_restart_after_a_completed_lifecycle() -> None:
    lifecycle = ServerLifecycle()
    for state in (ServerState.STARTING, ServerState.RUNNING, ServerState.STOPPING, ServerState.STOPPED):
        lifecycle.transition_to(state)

    lifecycle.transition_to(ServerState.STARTING)

    assert lifecycle.state is ServerState.STARTING


def test_graceful_shutdown_sequence() -> None:
    lifecycle = ServerLifecycle()
    for state in (ServerState.STARTING, ServerState.RUNNING, ServerState.STOPPING, ServerState.STOPPED):
        lifecycle.transition_to(state)

    assert lifecycle.state is ServerState.STOPPED


def test_forced_shutdown_sequence() -> None:
    lifecycle = ServerLifecycle()
    for state in (ServerState.STARTING, ServerState.RUNNING, ServerState.KILLING, ServerState.STOPPED):
        lifecycle.transition_to(state)

    assert lifecycle.state is ServerState.STOPPED
