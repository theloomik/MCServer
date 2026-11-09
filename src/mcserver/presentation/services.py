"""The backend services the GUI uses, built once by ``app.py``."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_creation import ServerCreation
from mcserver.application.server_management import ServerManagement
from mcserver.application.server_output import ServerOutputBuffer


class PresentationServices:
    """Application services handed to controllers and views.

    In degraded mode (Java could not be resolved) ``coordinator`` and
    ``output`` are ``None`` and ``java_problem`` explains why; configuration
    management and server creation still work.
    """

    def __init__(
        self,
        *,
        servers_root: Path,
        management: ServerManagement,
        server_creation: ServerCreation,
        coordinator: ServerCoordinator | None,
        output: ServerOutputBuffer | None,
        java_problem: str | None,
        closer: Callable[[], object],
    ) -> None:
        """Hold the services; ``closer`` releases backend resources on shutdown."""
        self.servers_root = servers_root
        self.management = management
        self.server_creation = server_creation
        self.coordinator = coordinator
        self.output = output
        self.java_problem = java_problem
        self._closer = closer
        self._closed = False

    @property
    def can_run_servers(self) -> bool:
        """Return whether servers can be started (Java was found)."""
        return self.coordinator is not None

    @property
    def closed(self) -> bool:
        """Return whether ``close`` has run."""
        return self._closed

    def close(self) -> None:
        """Release backend resources once; later calls do nothing."""
        if self._closed:
            return
        self._closed = True
        self._closer()
