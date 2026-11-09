"""In-memory backend pieces for presentation tests (no files, no Java)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event

from mcserver.application.errors import (
    InvalidSourceJar,
    ServerConfigurationAlreadyExists,
    ServerConfigurationNotFound,
    ServerConfigurationStorageError,
    ServerDirectoryAlreadyExists,
    ServerProvisioningError,
)
from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_creation import ServerCreation
from mcserver.application.server_management import ServerManagement
from mcserver.application.server_output import ServerOutputBuffer
from mcserver.application.server_provisioning import ServerProvisioning
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.presentation.services import PresentationServices


class BrokenStorage(ServerConfigurationStorageError):
    pass


class InMemoryRepository:
    """Repository fake following the port contract; ``broken`` makes every read fail."""

    def __init__(self, *configurations: ServerConfiguration) -> None:
        self.items = {configuration.server_id: configuration for configuration in configurations}
        self.broken = False
        self.broken_get = False
        self.broken_remove = False

    def list_all(self) -> tuple[ServerConfiguration, ...]:
        if self.broken:
            raise BrokenStorage("server_configurations.json is invalid: not valid JSON.")
        return tuple(self.items.values())

    def get(self, server_id: str) -> ServerConfiguration:
        if self.broken or self.broken_get:
            raise BrokenStorage("server_configurations.json is invalid: not valid JSON.")
        try:
            return self.items[server_id]
        except KeyError:
            raise ServerConfigurationNotFound(server_id) from None

    def add(self, configuration: ServerConfiguration) -> None:
        if configuration.server_id in self.items:
            raise ServerConfigurationAlreadyExists(configuration.server_id)
        self.items[configuration.server_id] = configuration

    def update(self, configuration: ServerConfiguration) -> None:
        self.items[configuration.server_id] = configuration

    def remove(self, server_id: str) -> None:
        if self.broken_remove:
            raise BrokenStorage("server_configurations.json could not be written: disk full.")
        self.items.pop(server_id)


class NoLegacySource:
    def list_server_ids(self) -> tuple[str, ...]:
        return ()

    def read_server(self, server_id: str) -> ServerConfiguration:
        raise AssertionError("not used")


class UnusedFilesystem:
    def __getattr__(self, name: str) -> Callable[..., None]:
        raise AssertionError(f"filesystem must not be used: {name}")


class MemoryFilesystem:
    """In-memory ``ServerProvisioningFilesystem``: folders map JAR names to their source path."""

    def __init__(self, *existing_directories: str) -> None:
        self.tree: dict[str, dict[str, str]] = {name: {} for name in existing_directories}
        self.calls: list[str] = []
        self.install_gate: Event | None = None
        self.install_error: ServerProvisioningError | None = None
        self.remove_error: ServerProvisioningError | None = None
        self.missing_sources: set[str] = set()

    def check_source_jar(self, source_jar: str) -> None:
        self.calls.append(f"check:{source_jar}")
        if source_jar in self.missing_sources:
            raise InvalidSourceJar(source_jar, "the file does not exist")

    def create_directory(self, directory: str) -> None:
        self.calls.append(f"create:{directory}")
        if directory in self.tree:
            raise ServerDirectoryAlreadyExists(directory)
        self.tree[directory] = {}

    def install_jar(self, directory: str, jar_file: str, source_jar: str) -> None:
        self.calls.append(f"install:{directory}/{jar_file}")
        if self.install_gate is not None:
            self.install_gate.wait(5)
        if self.install_error is not None:
            raise self.install_error
        self.tree[directory][jar_file] = source_jar

    def remove_created_directory(self, directory: str) -> None:
        self.calls.append(f"remove:{directory}")
        if self.remove_error is not None:
            raise self.remove_error
        if not self.tree.get(directory):
            self.tree.pop(directory, None)


class FakeRunner:
    """Process stand-in: start/stop succeed immediately unless told otherwise."""

    def __init__(self) -> None:
        self.on_exit: Callable[[int], None] | None = None
        self.start_gate: Event | None = None
        self.start_error: Exception | None = None
        self.stop_error: Exception | None = None
        self.crash_on_start = False
        self.started: list[str] = []
        self.stopped: list[float] = []

    def start(self, server_id: str, on_exit: Callable[[int], None]) -> None:
        self.started.append(server_id)
        if self.start_gate is not None:
            self.start_gate.wait(5)
        if self.start_error is not None:
            raise self.start_error
        self.on_exit = on_exit
        if self.crash_on_start:
            self.exit(1)  # the process dies before anyone could poll it

    def stop(self, timeout: float) -> None:
        self.stopped.append(timeout)
        if self.stop_error is not None:
            raise self.stop_error
        self.exit(0)

    def exit(self, code: int) -> None:
        """Simulate the process ending (normally or by crashing)."""
        on_exit, self.on_exit = self.on_exit, None
        if on_exit is not None:
            on_exit(code)


class FakeRunnerFactory:
    def __init__(self) -> None:
        self.runner = FakeRunner()

    def create(self, server_id: str) -> FakeRunner:
        return self.runner


def management_for(repository: InMemoryRepository) -> ServerManagement:
    return ServerManagement(repository, NoLegacySource())


def coordinator(factory: FakeRunnerFactory | None = None) -> ServerCoordinator:
    return ServerCoordinator(factory or FakeRunnerFactory())


def creation_for(repository: InMemoryRepository, filesystem: object) -> ServerCreation:
    """The real creation use case over in-memory storage and files."""
    management = management_for(repository)
    return ServerCreation(management, ServerProvisioning(repository, filesystem))  # type: ignore[arg-type]


def services_for(
    repository: InMemoryRepository,
    *,
    root: Path,
    java: bool = True,
    closes: list[str] | None = None,
    server_coordinator: ServerCoordinator | None = None,
    output: ServerOutputBuffer | None = None,
    filesystem: object | None = None,
) -> PresentationServices:
    calls = closes if closes is not None else []
    management = management_for(repository)
    return PresentationServices(
        servers_root=root,
        management=management,
        server_creation=creation_for(repository, filesystem or UnusedFilesystem()),
        coordinator=(server_coordinator or coordinator()) if java else None,
        output=(output or ServerOutputBuffer()) if java else None,
        java_problem=None if java else "No usable Java runtime was found.",
        closer=lambda: calls.append("closed"),
    )
