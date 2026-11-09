"""Manual dependency wiring for a configured Minecraft server runtime."""

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from mcserver.application.ports import ServerConfigurationRepository
from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_management import ServerManagement
from mcserver.application.server_output import DEFAULT_OUTPUT_CAPACITY, ServerOutputBuffer
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

    def close(self, timeout: float = 10.0) -> bool:
        """Stop the active server, then end output delivery.

        The output buffer is closed even if stopping the server fails, and the
        stop error is re-raised afterwards. Returns whether the output
        dispatcher thread has ended.
        """
        try:
            self.coordinator.stop_server(timeout)
        finally:
            dispatcher_stopped = self.output.close(timeout)
        return dispatcher_stopped

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
    java_resolver: JavaRuntimeResolver | None = None,
    output_capacity: int = DEFAULT_OUTPUT_CAPACITY,
    *,
    launch_from_configuration_store: bool = False,
) -> ServerRuntime:
    """Build a coordinator whose runners publish console output to a shared buffer.

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
    factory = ConfiguredServerRunnerFactory(settings_source, str(resolver.resolve().executable), output_sink=output)
    return ServerRuntime(
        coordinator=ServerCoordinator(factory),
        output=output,
        configurations=configurations,
        management=build_server_management(servers_directory, configurations),
    )


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
