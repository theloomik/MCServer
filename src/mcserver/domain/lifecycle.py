"""Pure domain model for the lifecycle of a Minecraft server."""

from enum import Enum
from types import MappingProxyType

from mcserver.domain.errors import InvalidStateTransition


class ServerState(str, Enum):
    """The possible states of a managed Minecraft server."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    KILLING = "killing"


_ALLOWED_TRANSITIONS: MappingProxyType[ServerState, frozenset[ServerState]] = MappingProxyType(
    {
        ServerState.STOPPED: frozenset({ServerState.STARTING}),
        ServerState.STARTING: frozenset({ServerState.RUNNING, ServerState.STOPPED, ServerState.KILLING}),
        ServerState.RUNNING: frozenset({ServerState.STOPPING, ServerState.STOPPED, ServerState.KILLING}),
        ServerState.STOPPING: frozenset({ServerState.STOPPED, ServerState.KILLING}),
        ServerState.KILLING: frozenset({ServerState.STOPPED}),
    }
)


class ServerLifecycle:
    """Maintain the valid state transitions of one Minecraft server lifecycle."""

    def __init__(self) -> None:
        """Create a lifecycle in its initial stopped state."""
        self._state = ServerState.STOPPED

    @property
    def state(self) -> ServerState:
        """Return the current lifecycle state."""
        return self._state

    def can_transition_to(self, target: ServerState) -> bool:
        """Return whether the lifecycle can transition from its current state to ``target``."""
        return target in _ALLOWED_TRANSITIONS[self._state]

    def transition_to(self, target: ServerState) -> None:
        """Move to ``target`` or raise an error without changing the current state."""
        if not self.can_transition_to(target):
            message = f"Cannot transition server lifecycle from {self._state.name} to {target.name}."
            raise InvalidStateTransition(message)
        self._state = target
