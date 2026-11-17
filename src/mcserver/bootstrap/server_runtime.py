"""Manual dependency wiring for a configured Minecraft server runtime."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from mcserver.application.errors import ServerStopTimedOut
from mcserver.application.java_setup import JavaSetup
from mcserver.application.ports import JavaRuntimeProvider, Scheduler, ServerConfigurationRepository
from mcserver.application.server_coordinator import (
    DEFAULT_STARTUP_TIMEOUT_SECONDS,
    DEFAULT_STOP_TIMEOUT_SECONDS,
    ServerCoordinator,
)
from mcserver.application.server_creation import ServerCreation
from mcserver.application.server_health import ServerHealth
from mcserver.application.server_management import ServerManagement
from mcserver.application.server_output import DEFAULT_OUTPUT_CAPACITY, ServerOutputBuffer
from mcserver.application.server_provisioning import ServerProvisioning
from mcserver.infrastructure.java_runtime import JavaRuntimeResolver
from mcserver.infrastructure.legacy_import import LegacyFileServerConfigurationSource
from mcserver.infrastructure.server_configuration import (
    ConfiguredServerRunnerFactory,
    LaunchSettingsSource,
    LegacyServerConfigurationRepository,
)
from mcserver.infrastructure.server_configuration_store import (
    JsonServerConfigurationRepository,
    StoredServerLaunchSettings,
)
from mcserver.infrastructure.server_files import LocalServerFilesystem
from mcserver.infrastructure.session_markers import FileSessionMarkerStore
from mcserver.infrastructure.windows_job import ProcessGuard, default_process_guard


@dataclass(frozen=True, slots=True)
class ServerRuntime:
    """The composed objects a presentation layer needs to control and observe servers.

    The runtime owns its parts: whoever builds it calls ``close`` (or uses it
    as a context manager) when the application shuts down.
    """

    coordinator: ServerCoordinator
    output: ServerOutputBuffer
    configurations: ServerConfigurationRepository
    management: ServerManagement
    """Configuration use cases sharing ``configurations`` (the same repository instance)."""
    provisioning: ServerProvisioning
    """Server file preparation reading from ``configurations`` (the same repository instance)."""
    server_creation: ServerCreation
    """One-step creation built from ``management`` and ``provisioning`` above."""
    java: JavaSetup
    """Java detection and the user's executable choice; looked up again on every start."""
    health: ServerHealth
    """Unclean-shutdown incidents from the previous session."""

    def close(self, timeout: float | None = None) -> bool:
        """Stop the active server gracefully, then end output delivery; never kills (ADR 0006).

        ``timeout`` defaults to the coordinator's stop timeout. Returns whether
        no server is left running and the output dispatcher has ended. If the
        stop times out the server keeps running and ``False`` is returned; when
        the application process then ends, the Windows Job Object terminates
        it and its session marker stays for the next launch. Other stop errors
        are re-raised after the output buffer was closed.
        """
        stopped = True
        try:
            self.coordinator.stop_server(timeout)
        except ServerStopTimedOut:
            stopped = False
        finally:
            dispatcher_stopped = self.output.close(10.0 if timeout is None else max(timeout, 1.0))
        return stopped and dispatcher_stopped

    def __enter__(self) -> "ServerRuntime":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def build_server_runtime(
    servers_directory: Path,
    java_resolver: JavaRuntimeProvider | None = None,
    output_capacity: int = DEFAULT_OUTPUT_CAPACITY,
    *,
    launch_from_configuration_store: bool = False,
    scheduler: Scheduler | None = None,
    startup_timeout: float = DEFAULT_STARTUP_TIMEOUT_SECONDS,
    stop_timeout: float = DEFAULT_STOP_TIMEOUT_SECONDS,
    process_guard_factory: Callable[[], ProcessGuard] = default_process_guard,
) -> ServerRuntime:
    """Build a coordinator whose runners publish console output to a shared buffer.

    Java is not resolved here: the runner factory looks it up on every start,
    so a missing Java no longer prevents building the runtime (M1-BE-05).
    ``runtime.configurations`` always exposes the versioned configuration
    store. Servers are launched from the legacy ``servers_config.json`` unless
    ``launch_from_configuration_store`` is set, which switches launching to the
    new store (for use once configurations have been imported).
    """
    output = ServerOutputBuffer(output_capacity)
    configurations = JsonServerConfigurationRepository(servers_directory)
    settings_source: LaunchSettingsSource
    if launch_from_configuration_store:
        settings_source = StoredServerLaunchSettings(configurations, servers_directory)
    else:
        settings_source = LegacyServerConfigurationRepository(servers_directory)
    resolver = java_resolver or JavaRuntimeResolver.for_current_application()
    factory = ConfiguredServerRunnerFactory(
        settings_source, resolver, output_sink=output, process_guard_factory=process_guard_factory
    )
    markers = FileSessionMarkerStore(servers_directory, configurations)
    management = build_server_management(servers_directory, configurations)
    provisioning = build_server_provisioning(servers_directory, configurations)
    coordinator = ServerCoordinator(
        factory,
        scheduler=scheduler,
        markers=markers,
        startup_timeout=startup_timeout,
        stop_timeout=stop_timeout,
    )
    return ServerRuntime(
        coordinator=coordinator,
        output=output,
        configurations=configurations,
        management=management,
        provisioning=provisioning,
        server_creation=ServerCreation(management, provisioning),
        java=JavaSetup(resolver),
        health=ServerHealth(markers),
    )


def build_server_creation(
    servers_directory: Path, repository: ServerConfigurationRepository | None = None
) -> ServerCreation:
    """Build one-step server creation for ``servers_directory`` without resolving Java.

    Management and provisioning share one repository instance; pass
    ``repository`` to share an existing one, as ``build_server_runtime`` does.
    """
    configurations = JsonServerConfigurationRepository(servers_directory) if repository is None else repository
    return ServerCreation(
        build_server_management(servers_directory, configurations),
        build_server_provisioning(servers_directory, configurations),
    )


def build_server_provisioning(
    servers_directory: Path, repository: ServerConfigurationRepository | None = None
) -> ServerProvisioning:
    """Build server file provisioning for ``servers_directory`` without resolving Java.

    Pass ``repository`` to share an existing repository instance, as
    ``build_server_runtime`` does.
    """
    configurations = JsonServerConfigurationRepository(servers_directory) if repository is None else repository
    return ServerProvisioning(configurations, LocalServerFilesystem(servers_directory))


def build_server_management(
    servers_directory: Path, repository: ServerConfigurationRepository | None = None
) -> ServerManagement:
    """Build configuration use cases for ``servers_directory`` without resolving Java.

    Pass ``repository`` to share an existing repository instance (as
    ``build_server_runtime`` does); within one process, use a single instance
    per servers directory so writes stay serialised. Legacy import only runs
    when ``import_legacy_servers`` is called.
    """
    configurations = JsonServerConfigurationRepository(servers_directory) if repository is None else repository
    legacy_source = LegacyFileServerConfigurationSource(LegacyServerConfigurationRepository(servers_directory))
    return ServerManagement(configurations, legacy_source)


def build_server_coordinator(
    servers_directory: Path, java_resolver: JavaRuntimeResolver | None = None
) -> ServerCoordinator:
    """Build a coordinator that creates runners from existing configuration and Java.

    Prefer ``build_server_runtime`` when console output is needed; this
    coordinator's output buffer has no subscribers, so no dispatcher starts.
    """
    return build_server_runtime(servers_directory, java_resolver).coordinator
