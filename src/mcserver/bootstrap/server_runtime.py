"""Manual dependency wiring for a configured Minecraft server runtime."""

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_output import DEFAULT_OUTPUT_CAPACITY, ServerOutputBuffer
from mcserver.infrastructure.java_runtime import JavaRuntimeResolver
from mcserver.infrastructure.server_configuration import (
    ConfiguredServerRunnerFactory,
    LegacyServerConfigurationRepository,
)


@dataclass(frozen=True, slots=True)
class ServerRuntime:
    """The composed objects a presentation layer needs to control and observe servers.

    The runtime owns its parts: whoever builds it calls ``close`` (or uses it
    as a context manager) when the application shuts down.
    """

    coordinator: ServerCoordinator
    output: ServerOutputBuffer

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
    """Build a coordinator that creates runners from existing configuration and Java.

    Prefer ``build_server_runtime`` when console output is needed; this
    coordinator's output buffer has no subscribers, so no dispatcher starts.
    """
    return build_server_runtime(servers_directory, java_resolver).coordinator
