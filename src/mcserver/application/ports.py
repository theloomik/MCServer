"""Application ports implemented by infrastructure adapters."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from mcserver.domain.server_configuration import ServerConfiguration

ProcessExitHandler = Callable[[int], None]


class OutputStream(Enum):
    """The process stream a console line was read from."""

    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass(frozen=True, slots=True)
class ServerOutputLine:
    """One console line produced by a server process.

    ``sequence`` increases monotonically per output buffer so consumers can
    order lines and discard duplicates after a replay.
    """

    sequence: int
    server_id: str
    stream: OutputStream
    text: str


ServerOutputListener = Callable[[ServerOutputLine], None]


class ServerOutputSink(Protocol):
    """Receive console lines from a running server process."""

    def publish(self, server_id: str, stream: OutputStream, text: str) -> None:
        """Record one console line without its trailing newline."""


class ServerRunner(Protocol):
    """Start and stop a server process without exposing process APIs to use cases."""

    def start(self, server_id: str, on_exit: ProcessExitHandler) -> None:
        """Start ``server_id`` and notify ``on_exit`` once its process exits."""

    def stop(self, timeout: float) -> None:
        """Request graceful shutdown, forcing termination after ``timeout`` seconds."""


class ServerRunnerFactory(Protocol):
    """Create a runner configured for a selected server."""

    def create(self, server_id: str) -> ServerRunner:
        """Return a new runner configured for ``server_id``."""


class ServerConfigurationRepository(Protocol):
    """Store server configurations by ``server_id``.

    ``get``, ``update`` and ``remove`` raise ``ServerConfigurationNotFound``
    for an unknown identifier; ``add`` raises ``ServerConfigurationAlreadyExists``
    for a taken one. ``add`` and ``update`` raise ``ServerDirectoryInUse`` when
    another server already uses the same directory (compared case-insensitively,
    as on Windows). Storage failures raise ``ServerConfigurationStorageError``.
    """

    def list_all(self) -> tuple[ServerConfiguration, ...]:
        """Return every stored configuration in a stable order."""

    def get(self, server_id: str) -> ServerConfiguration:
        """Return the configuration stored for ``server_id``."""

    def add(self, configuration: ServerConfiguration) -> None:
        """Store a configuration for a new server."""

    def update(self, configuration: ServerConfiguration) -> None:
        """Replace the stored configuration with the same ``server_id``."""

    def remove(self, server_id: str) -> None:
        """Delete the configuration stored for ``server_id``."""


class LegacyServerConfigurationSource(Protocol):
    """Read-only access to server configurations kept in the legacy format.

    ``list_server_ids`` raises ``LegacyConfigurationUnavailable`` when legacy
    data exists but cannot be read, and returns an empty tuple when there is
    none. ``read_server`` raises ``LegacyServerEntryInvalid`` (or the domain's
    ``InvalidServerConfiguration``) for an entry that cannot be converted.
    """

    def list_server_ids(self) -> tuple[str, ...]:
        """Return the identifiers of all legacy server entries, in source order."""

    def read_server(self, server_id: str) -> ServerConfiguration:
        """Convert one legacy entry into a configuration."""


class ServerProvisioningFilesystem(Protocol):
    """Prepare server files inside the managed servers root.

    ``directory`` and ``jar_file`` are names relative to the root, as stored in
    ``ServerConfiguration``; ``source_jar`` is a path chosen by the user. All
    failures raise ``ServerProvisioningError`` subclasses. An operation that
    fails cleans up what it created itself; whatever it could not remove is
    reported in the error's ``leftovers``.
    """

    def check_source_jar(self, source_jar: str) -> None:
        """Raise ``InvalidSourceJar`` unless ``source_jar`` is an existing regular ``.jar`` file."""

    def create_directory(self, directory: str) -> None:
        """Create a new, empty server directory.

        Raises ``ServerDirectoryAlreadyExists`` if anything with that name exists.
        """

    def install_jar(self, directory: str, jar_file: str, source_jar: str) -> None:
        """Copy ``source_jar`` to ``directory/jar_file`` without overwriting.

        Raises ``ServerJarAlreadyExists`` if the destination exists. A partial
        copy is removed on failure.
        """

    def remove_created_directory(self, directory: str) -> None:
        """Remove a directory created by ``create_directory``, only if it is still empty."""
