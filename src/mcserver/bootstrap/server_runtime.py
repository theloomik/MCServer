"""Manual dependency wiring for a configured Minecraft server runtime."""

from dataclasses import dataclass
from pathlib import Path

from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_output import DEFAULT_OUTPUT_CAPACITY, ServerOutputBuffer
from mcserver.infrastructure.java_runtime import JavaRuntimeResolver
from mcserver.infrastructure.server_configuration import (
    ConfiguredServerRunnerFactory,
    LegacyServerConfigurationRepository,
)


@dataclass(frozen=True, slots=True)
class ServerRuntime:
    """The composed objects a presentation layer needs to control and observe servers."""

    coordinator: ServerCoordinator
    output: ServerOutputBuffer


def build_server_runtime(
    servers_directory: Path,
    java_resolver: JavaRuntimeResolver | None = None,
    output_capacity: int = DEFAULT_OUTPUT_CAPACITY,
) -> ServerRuntime:
    """Build a coordinator whose runners publish console output to a shared buffer."""
    output = ServerOutputBuffer(output_capacity)
    repository = LegacyServerConfigurationRepository(servers_directory)
    resolver = java_resolver or JavaRuntimeResolver.for_current_application()
    factory = ConfiguredServerRunnerFactory(repository, str(resolver.resolve().executable), output_sink=output)
    return ServerRuntime(coordinator=ServerCoordinator(factory), output=output)


def build_server_coordinator(
    servers_directory: Path, java_resolver: JavaRuntimeResolver | None = None
) -> ServerCoordinator:
    """Build a coordinator that creates runners from existing configuration and Java."""
    return build_server_runtime(servers_directory, java_resolver).coordinator
