"""Use cases for managing stored server configurations."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum

from mcserver.application.errors import (
    LegacyServerEntryInvalid,
    ServerConfigurationAlreadyExists,
    ServerDirectoryInUse,
    ServerFilesRemovalFailed,
    ServerIsRunning,
)
from mcserver.application.ports import (
    LegacyServerConfigurationSource,
    RemovedServerFiles,
    ServerConfigurationRepository,
    ServerFilesRemover,
)
from mcserver.domain.errors import InvalidServerConfiguration
from mcserver.domain.server_configuration import ServerConfiguration


class _Unset(Enum):
    UNSET = "unset"


UNSET = _Unset.UNSET
"""Marks an ``update_server`` argument that was not given (``None`` clears optional values)."""


@dataclass(frozen=True, slots=True)
class DeletedServer:
    """Result of ``delete_server``: where the files went, when they were removed."""

    server_id: str
    files: RemovedServerFiles | None
    """``None`` when only the configuration was removed and the files stayed in place."""


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
    * ``LegacyConfigurationUnavailable``: legacy data could not be read for import;
    * ``ServerIsRunning``: the change is not allowed while that server is active;
    * ``ServerFilesRemovalFailed``: server files could not be moved away; nothing was deleted.

    The exception is ``delete_server(remove_files=True)``, which moves the
    server folder to the Windows Recycle Bin (or the ``.trash`` fallback)
    through ``ServerFilesRemover``. Files are never deleted permanently.
    """

    def __init__(
        self,
        repository: ServerConfigurationRepository,
        legacy_source: LegacyServerConfigurationSource,
        *,
        active_server: Callable[[], str | None] = lambda: None,
        files_remover: ServerFilesRemover | None = None,
    ) -> None:
        """Manage configurations in ``repository``; ``active_server`` tells which server runs now."""
        self._repository = repository
        self._legacy_source = legacy_source
        self._active_server = active_server
        self._files_remover = files_remover

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
        display_name: str | None = None,
        jvm_arguments: tuple[str, ...] | None = None,
        java_path: str | None | _Unset = UNSET,
        server_type: str | None | _Unset = UNSET,
        minecraft_version: str | None | _Unset = UNSET,
    ) -> ServerConfiguration:
        """Change the given settings of an existing server and return the stored result (M2-BE-02).

        Omitted settings keep their current values; for the optional ones
        (``java_path``, ``server_type``, ``minecraft_version``) ``None`` clears
        them. The ``server_id`` cannot change; renaming changes
        ``display_name``. Changing ``directory`` only re-points the
        configuration; no files are moved. While the server is active,
        ``directory`` and ``jar_file`` cannot change (``ServerIsRunning``);
        everything else applies on its next start.
        """
        current = self._repository.get(server_id)
        changes: dict[str, object] = {}
        for name, value in (
            ("directory", directory),
            ("jar_file", jar_file),
            ("memory_mb", memory_mb),
            ("display_name", display_name),
            ("jvm_arguments", jvm_arguments),
        ):
            if value is not None:
                changes[name] = value
        for name, optional in (
            ("java_path", java_path),
            ("server_type", server_type),
            ("minecraft_version", minecraft_version),
        ):
            if optional is not UNSET:
                changes[name] = optional
        moves_files = any(
            name in changes and changes[name] != getattr(current, name) for name in ("directory", "jar_file")
        )
        if moves_files and self._active_server() == server_id:
            raise ServerIsRunning(server_id)
        updated = replace(current, **changes)  # type: ignore[arg-type]  # domain validation runs again
        self._repository.update(updated)
        return updated

    def delete_server(self, server_id: str, *, remove_files: bool = False) -> DeletedServer:
        """Remove ``server_id``; with ``remove_files`` its folder goes to the Recycle Bin first (M2-BE-03).

        Refused while the server is active. Files are moved before the
        configuration is removed: if moving fails, nothing changes
        (``ServerFilesRemovalFailed``); if removing the configuration then
        fails, the files can be restored from where ``files`` says they are.
        """
        configuration = self._repository.get(server_id)
        if self._active_server() == server_id:
            raise ServerIsRunning(server_id)
        files: RemovedServerFiles | None = None
        if remove_files:
            if self._files_remover is None:
                raise ServerFilesRemovalFailed(configuration.directory, "file removal is not available")
            files = self._files_remover.remove_server_files(configuration.directory)
        self._repository.remove(server_id)
        return DeletedServer(server_id, files)

    def pending_legacy_servers(self) -> tuple[str, ...]:
        """Return legacy server identifiers that are not stored yet (what an import would offer)."""
        present = {configuration.server_id for configuration in self._repository.list_all()}
        return tuple(server_id for server_id in self._legacy_source.list_server_ids() if server_id not in present)

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
