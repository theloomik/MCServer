"""Use case for coordinating the single active Minecraft server."""

from threading import RLock

from mcserver.application.errors import ActiveServerAlreadyExists, ServerStartFailed, ServerStopFailed
from mcserver.application.ports import ServerRunner, ServerRunnerFactory
from mcserver.domain.lifecycle import ServerLifecycle, ServerState


class ServerCoordinator:
    """Coordinate starting one server while enforcing the single-active-server policy."""

    def __init__(self, runner_factory: ServerRunnerFactory, lifecycle: ServerLifecycle | None = None) -> None:
        """Create a coordinator with an injected runner factory and optional lifecycle."""
        self._runner_factory = runner_factory
        self._server_runner: ServerRunner | None = None
        self._lifecycle = lifecycle or ServerLifecycle()
        self._active_server_id: str | None = None
        self._lock = RLock()

    @property
    def active_server_id(self) -> str | None:
        """Return the server currently starting or active, if any."""
        with self._lock:
            return self._active_server_id

    @property
    def state(self) -> ServerState:
        """Return the lifecycle state of the active-server coordinator."""
        with self._lock:
            return self._lifecycle.state

    def start_server(self, server_id: str) -> None:
        """Request a server start and record it as the sole server currently starting.

        The lifecycle moves to ``STARTING`` only for a request accepted by the
        application. A starter failure returns it to ``STOPPED`` and releases the
        active-server reservation.
        """
        with self._lock:
            if self._active_server_id is not None:
                raise ActiveServerAlreadyExists(self._active_server_id)

            self._lifecycle.transition_to(ServerState.STARTING)
            self._active_server_id = server_id
            try:
                runner = self._runner_factory.create(server_id)
                self._server_runner = runner
                runner.start(server_id, lambda exit_code: self._on_process_exit(server_id, exit_code))
            except Exception as error:
                self._release_active_server(server_id)
                raise ServerStartFailed(server_id) from error

            if self._active_server_id == server_id and self._lifecycle.state is ServerState.STARTING:
                self._lifecycle.transition_to(ServerState.RUNNING)

    def stop_server(self, timeout: float = 10.0) -> bool:
        """Stop the active server and return whether a stop request was made.

        Calling this method when no server is active is safe and returns ``False``.
        """
        with self._lock:
            server_id = self._active_server_id
            if server_id is None:
                return False
            if self._lifecycle.state is ServerState.RUNNING:
                self._lifecycle.transition_to(ServerState.STOPPING)

        try:
            runner = self._server_runner
            if runner is None:
                return False
            runner.stop(timeout)
        except Exception as error:
            with self._lock:
                self._release_active_server(server_id)
            raise ServerStopFailed(server_id) from error

        with self._lock:
            self._release_active_server(server_id)
        return True

    def _on_process_exit(self, server_id: str, _exit_code: int) -> None:
        """Release the active-server reservation after a runner reports process exit."""
        with self._lock:
            self._release_active_server(server_id)

    def _release_active_server(self, server_id: str) -> None:
        """Transition to stopped and clear ``server_id`` when it remains active."""
        if self._active_server_id != server_id:
            return
        if self._lifecycle.state is not ServerState.STOPPED:
            self._lifecycle.transition_to(ServerState.STOPPED)
        self._active_server_id = None
        self._server_runner = None
