"""Manual dependency wiring for a configured Minecraft server runtime."""

from pathlib import Path

from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.infrastructure.java_runtime import JavaRuntimeResolver
from mcserver.infrastructure.server_configuration import (
    ConfiguredServerRunnerFactory,
    LegacyServerConfigurationRepository,
)


def build_server_coordinator(
    servers_directory: Path, java_resolver: JavaRuntimeResolver | None = None
) -> ServerCoordinator:
    """Build a coordinator that creates runners from existing configuration and Java."""
    repository = LegacyServerConfigurationRepository(servers_directory)
    resolver = java_resolver or JavaRuntimeResolver.for_current_application()
    factory = ConfiguredServerRunnerFactory(repository, str(resolver.resolve().executable))
    return ServerCoordinator(factory)
