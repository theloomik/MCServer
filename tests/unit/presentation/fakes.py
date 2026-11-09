"""In-memory backend pieces for presentation tests (no files, no Java)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mcserver.application.errors import (
    ServerConfigurationAlreadyExists,
    ServerConfigurationNotFound,
    ServerConfigurationStorageError,
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
        self.items.pop(server_id)


class NoLegacySource:
    def list_server_ids(self) -> tuple[str, ...]:
        return ()

    def read_server(self, server_id: str) -> ServerConfiguration:
        raise AssertionError("not used")


class UnusedFilesystem:
    def __getattr__(self, name: str) -> Callable[..., None]:
        raise AssertionError(f"filesystem must not be used: {name}")


class FakeRunner:
    def __init__(self) -> None:
        self.on_exit: Callable[[int], None] | None = None

    def start(self, server_id: str, on_exit: Callable[[int], None]) -> None:
        self.on_exit = on_exit

    def stop(self, timeout: float) -> None:
        if self.on_exit is not None:
            self.on_exit(0)


class FakeRunnerFactory:
    def __init__(self) -> None:
        self.runner = FakeRunner()

    def create(self, server_id: str) -> FakeRunner:
        return self.runner


def management_for(repository: InMemoryRepository) -> ServerManagement:
    return ServerManagement(repository, NoLegacySource())


def coordinator() -> ServerCoordinator:
    return ServerCoordinator(FakeRunnerFactory())


def services_for(
    repository: InMemoryRepository,
    *,
    root: Path,
    java: bool = True,
    closes: list[str] | None = None,
    server_coordinator: ServerCoordinator | None = None,
) -> PresentationServices:
    calls = closes if closes is not None else []
    management = management_for(repository)
    return PresentationServices(
        servers_root=root,
        management=management,
        server_creation=ServerCreation(management, ServerProvisioning(repository, UnusedFilesystem())),
        coordinator=(server_coordinator or coordinator()) if java else None,
        output=ServerOutputBuffer() if java else None,
        java_problem=None if java else "No usable Java runtime was found.",
        closer=lambda: calls.append("closed"),
    )
