"""Use case for coordinating the single active Minecraft server."""

from mcserver.application.errors import ActiveServerAlreadyExists, ServerStartFailed
from mcserver.application.ports import ServerStarter
from mcserver.domain.lifecycle import ServerLifecycle, ServerState


class ServerCoordinator:
    """Coordinate starting one server while enforcing the single-active-server policy."""

    def __init__(self, server_starter: ServerStarter, lifecycle: ServerLifecycle | None = None) -> None:
        """Create a coordinator with an injected starter and optional lifecycle instance."""
        self._server_starter = server_starter
        self._lifecycle = lifecycle or ServerLifecycle()
        self._active_server_id: str | None = None

    @property
    def active_server_id(self) -> str | None:
        """Return the server currently starting or active, if any."""
        return self._active_server_id

    @property
    def state(self) -> ServerState:
        """Return the lifecycle state of the active-server coordinator."""
        return self._lifecycle.state

    def start_server(self, server_id: str) -> None:
        """Request a server start and record it as the sole server currently starting.

        The lifecycle moves to ``STARTING`` only for a request accepted by the
        application. A starter failure returns it to ``STOPPED`` and releases the
        active-server reservation.
        """
        if self._active_server_id is not None:
            raise ActiveServerAlreadyExists(self._active_server_id)

        self._lifecycle.transition_to(ServerState.STARTING)
        self._active_server_id = server_id
        try:
            self._server_starter.start(server_id)
        except Exception as error:
            self._lifecycle.transition_to(ServerState.STOPPED)
            self._active_server_id = None
            raise ServerStartFailed(server_id) from error
