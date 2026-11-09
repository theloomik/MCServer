"""Manual dependency wiring for a configured Minecraft server runtime."""

from pathlib import Path

from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.infrastructure.server_configuration import (
    ConfiguredServerRunnerFactory,
    LegacyServerConfigurationRepository,
)


def build_server_coordinator(servers_directory: Path, java_executable: str) -> ServerCoordinator:
    """Build a coordinator that creates runners from existing server configuration."""
    repository = LegacyServerConfigurationRepository(servers_directory)
    factory = ConfiguredServerRunnerFactory(repository, java_executable)
    return ServerCoordinator(factory)
