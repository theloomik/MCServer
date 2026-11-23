"""The backend services the GUI uses, built once by ``app.py``."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mcserver.application.auto_restart import AutoRestartPolicy
from mcserver.application.backups import BackupService
from mcserver.application.java_setup import JavaSetup
from mcserver.application.server_activity import ServerActivity
from mcserver.application.server_address import ServerAddressLookup
from mcserver.application.server_adoption import ServerAdoption
from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_creation import ServerCreation
from mcserver.application.server_health import ServerHealth
from mcserver.application.server_management import ServerManagement
from mcserver.application.server_metrics import ServerMetrics
from mcserver.application.server_output import ServerOutputBuffer
from mcserver.application.server_properties import ServerPropertiesService
from mcserver.application.server_provisioning import ServerProvisioning
from mcserver.application.settings import SettingsService


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
        provisioning: ServerProvisioning | None = None,
        java: JavaSetup | None = None,
        health: ServerHealth | None = None,
        settings: SettingsService | None = None,
        adoption: ServerAdoption | None = None,
        properties: ServerPropertiesService | None = None,
        metrics: ServerMetrics | None = None,
        backups: BackupService | None = None,
        activity: ServerActivity | None = None,
        auto_restart: AutoRestartPolicy | None = None,
        address: ServerAddressLookup | None = None,
    ) -> None:
        """Hold the services; ``closer`` releases backend resources on shutdown."""
        self.servers_root = servers_root
        self.management = management
        self.server_creation = server_creation
        self.coordinator = coordinator
        self.output = output
        self.java_problem = java_problem
        self.provisioning = provisioning
        """Accepts the EULA for existing servers (``None`` in tests that do not need it)."""
        self.java = java
        """Java detection and the user's choice of ``java.exe``."""
        self.health = health
        """Unclean-shutdown incidents from the previous session."""
        self.settings = settings
        """Application settings (Java, timeouts, one-time legacy import offer)."""
        self.adoption = adoption
        """Imports existing server folders."""
        self.properties = properties
        """Reads and changes server.properties."""
        self.metrics = metrics
        """CPU, memory and uptime of the running server."""
        self.backups = backups
        """Backups and restores."""
        self.activity = activity
        """Players online and tick rate."""
        self.auto_restart = auto_restart
        """Opt-in restart after a crash."""
        self.address = address
        """LAN address and port of a server."""
        self.crashed = False
        """Set when an unhandled exception ends the application (the graceful stop was already tried)."""
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
