"""Use cases for managing stored server configurations."""

from dataclasses import dataclass

from mcserver.application.errors import (
    LegacyServerEntryInvalid,
    ServerConfigurationAlreadyExists,
    ServerDirectoryInUse,
)
from mcserver.application.ports import LegacyServerConfigurationSource, ServerConfigurationRepository
from mcserver.domain.errors import InvalidServerConfiguration
from mcserver.domain.server_configuration import ServerConfiguration


@dataclass(frozen=True, slots=True)
class RejectedLegacyServer:
    """A legacy entry that was not imported, with a human-readable reason."""

    server_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class LegacyImportResult:
    """Outcome of one legacy import, in legacy source order."""

    imported: tuple[str, ...]
    skipped: tuple[str, ...]
    """Servers already present in the repository; they were left unchanged."""
    rejected: tuple[RejectedLegacyServer, ...]

    @property
    def imported_count(self) -> int:
        """Return how many servers were added."""
        return len(self.imported)

    @property
    def skipped_count(self) -> int:
        """Return how many servers already existed and were kept as they are."""
        return len(self.skipped)

    @property
    def rejected_count(self) -> int:
        """Return how many legacy entries could not be imported."""
        return len(self.rejected)


class ServerManagement:
    """Create, read, update and delete server configurations, and import legacy ones.

    Only configuration records are managed: no method creates, moves or
    deletes server directories, JAR files or other user files.

    Errors are raised, never returned as ``None``:

    * ``InvalidServerConfiguration`` (domain): values break a business rule;
    * ``ServerConfigurationNotFound``: no server has the given ``server_id``;
    * ``ServerConfigurationAlreadyExists``: ``create_server`` with a taken ``server_id``;
    * ``ServerDirectoryInUse``: another server already uses the directory;
    * ``ServerConfigurationStorageError``: the repository's storage failed;
    * ``LegacyConfigurationUnavailable``: legacy data could not be read for import.
    """

    def __init__(
        self, repository: ServerConfigurationRepository, legacy_source: LegacyServerConfigurationSource
    ) -> None:
        """Manage configurations in ``repository`` and import from ``legacy_source``."""
        self._repository = repository
        self._legacy_source = legacy_source

    def list_servers(self) -> tuple[ServerConfiguration, ...]:
        """Return all stored configurations in the repository's stable order."""
        return self._repository.list_all()

    def get_server(self, server_id: str) -> ServerConfiguration:
        """Return the configuration of ``server_id``."""
        return self._repository.get(server_id)

    def create_server(self, *, server_id: str, directory: str, jar_file: str, memory_mb: int) -> ServerConfiguration:
        """Store a new server configuration and return it; never overwrites an existing one."""
        configuration = ServerConfiguration(
            server_id=server_id, directory=directory, jar_file=jar_file, memory_mb=memory_mb
        )
        self._repository.add(configuration)
        return configuration

    def update_server(
        self,
        server_id: str,
        *,
        directory: str | None = None,
        jar_file: str | None = None,
        memory_mb: int | None = None,
    ) -> ServerConfiguration:
        """Change the given settings of an existing server and return the stored result.

        Omitted settings keep their current values. The ``server_id`` cannot
        change. Changing ``directory`` only re-points the configuration; no
        files are moved.
        """
        current = self._repository.get(server_id)
        updated = ServerConfiguration(  # domain validation runs for the new values
            server_id=current.server_id,
            directory=current.directory if directory is None else directory,
            jar_file=current.jar_file if jar_file is None else jar_file,
            memory_mb=current.memory_mb if memory_mb is None else memory_mb,
        )
        self._repository.update(updated)
        return updated

    def delete_server(self, server_id: str) -> None:
        """Remove the configuration of ``server_id``; server files stay on disk."""
        self._repository.remove(server_id)

    def import_legacy_servers(self) -> LegacyImportResult:
        """Copy legacy servers that are valid and not yet stored; run only on explicit request.

        Repeating the import is safe: servers already in the repository are
        skipped and never overwritten. Invalid legacy entries are rejected
        individually without stopping the import. Unreadable legacy data or a
        storage failure stops the import with an exception; servers stored
        before that point remain, and a later run continues from there. The
        legacy data itself is only read.
        """
        present = {configuration.server_id for configuration in self._repository.list_all()}
        imported: list[str] = []
        skipped: list[str] = []
        rejected: list[RejectedLegacyServer] = []

        for server_id in self._legacy_source.list_server_ids():
            if server_id in present:
                skipped.append(server_id)
                continue
            try:
                self._repository.add(self._legacy_source.read_server(server_id))
            except ServerConfigurationAlreadyExists:
                skipped.append(server_id)
                continue
            except LegacyServerEntryInvalid as error:
                rejected.append(RejectedLegacyServer(server_id, error.reason))
                continue
            except (InvalidServerConfiguration, ServerDirectoryInUse) as error:
                rejected.append(RejectedLegacyServer(server_id, str(error)))
                continue
            imported.append(server_id)
            present.add(server_id)

        return LegacyImportResult(tuple(imported), tuple(skipped), tuple(rejected))
