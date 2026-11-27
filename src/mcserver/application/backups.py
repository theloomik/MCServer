"""Use case: create, list, restore and delete server backups (M3-BE-03, ADR 0008)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from mcserver.application.errors import ServerIsRunning
from mcserver.application.ports import RemovedServerFiles, ServerConfigurationRepository
from mcserver.application.progress import CancelToken, ProgressReporter, Stage, report, stage_callback
from mcserver.domain.lifecycle import ServerState

_logger = logging.getLogger(__name__)

SAVE_CONFIRMATION_TIMEOUT_SECONDS = 120.0
BackupProgress = Callable[[int, int], None]
"""Called with (bytes done, total bytes)."""


class BackupKind(str, Enum):
    """Why a backup was made."""

    MANUAL = "manual"
    SAFETY = "safety"
    """Made automatically right before a restore."""
    SCHEDULED = "scheduled"


@dataclass(frozen=True, slots=True)
class BackupInfo:
    """Metadata of one backup archive."""

    backup_id: str
    server_id: str
    created_at: str
    """ISO-8601 time in UTC."""
    size_bytes: int
    kind: BackupKind
    note: str = ""
    online: bool = False
    """Made while the server ran (world saving was paused for it)."""


class BackupError(RuntimeError):
    """Base for backup failures; nothing was changed when it is raised."""


class BackupNotPossible(BackupError):
    """Raised when the server is starting or stopping, so no consistent backup can be made now."""

    def __init__(self, server_id: str) -> None:
        """Describe the server that is in transition."""
        self.server_id = server_id
        super().__init__(f"Server '{server_id}' is starting or stopping; try again when it is running or stopped.")


class BackupFailed(BackupError):
    """Raised when a backup or restore could not be completed; ``reason`` says why."""

    def __init__(self, server_id: str, reason: str) -> None:
        """Describe the failure."""
        self.server_id = server_id
        self.reason = reason
        super().__init__(f"Backup operation for '{server_id}' failed: {reason}")


class BackupNotFound(BackupError):
    """Raised when a backup identifier does not exist for that server."""

    def __init__(self, server_id: str, backup_id: str) -> None:
        """Describe the missing backup."""
        self.server_id = server_id
        self.backup_id = backup_id
        super().__init__(f"Backup '{backup_id}' of server '{server_id}' does not exist.")


class BackupStore(Protocol):
    """Archive storage. Implementations never delete server files permanently.

    ``restore_backup`` replaces the server folder from the archive through a
    staging folder and a swap; the replaced data is moved to the Recycle Bin
    (or the trash folder), never deleted. ``recover_interrupted_restores``
    repairs a restore that was cut off by a crash.
    """

    def list_backups(self, server_id: str) -> tuple[BackupInfo, ...]:
        """Return the backups of ``server_id``, newest first."""

    def create_backup(
        self,
        server_id: str,
        directory: str,
        kind: BackupKind,
        note: str,
        online: bool,
        created_at: datetime,
        progress: BackupProgress | None,
    ) -> BackupInfo:
        """Archive the server folder ``directory``; raise ``BackupFailed`` and leave nothing on failure."""

    def restore_backup(self, server_id: str, directory: str, backup_id: str, progress: BackupProgress | None) -> None:
        """Replace the server folder with the archive's content; raise ``BackupFailed`` keeping the original."""

    def delete_backup(self, server_id: str, backup_id: str) -> RemovedServerFiles:
        """Move the archive to the Recycle Bin (or trash)."""

    def recover_interrupted_restores(self) -> tuple[str, ...]:
        """Repair restores interrupted by a crash; return the affected server folders."""


class CoordinatorView(Protocol):
    """What backups need from the coordinator."""

    @property
    def active_server_id(self) -> str | None:
        """Return the active server."""

    @property
    def state(self) -> ServerState:
        """Return the active server's state."""

    def send_command(self, server_id: str, command: str) -> None:
        """Send a console command."""

    def send_and_wait_for_line(
        self, server_id: str, command: str, predicate: Callable[[str], bool], timeout: float
    ) -> bool:
        """Send a command and wait for a matching console line."""


class BackupService:
    """Make consistent backups and restore them safely.

    * A stopped server is archived directly.
    * A running server is archived **online**: world saving is paused
      (``save-off``), everything is flushed (``save-all flush`` until the server
      confirms "Saved the game"), the folder is archived, and saving is turned
      back on (``save-on``) whatever happens.
    * A server that is starting or stopping cannot be backed up.
    * A restore is only possible while the server is stopped and always makes
      a safety backup of the current state first.
    """

    def __init__(
        self,
        repository: ServerConfigurationRepository,
        coordinator: CoordinatorView,
        store: BackupStore,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        save_timeout: float = SAVE_CONFIRMATION_TIMEOUT_SECONDS,
    ) -> None:
        """Use ``store`` for archives and ``coordinator`` to pause saving of a running server."""
        self._repository = repository
        self._coordinator = coordinator
        self._store = store
        self._clock = clock
        self._save_timeout = save_timeout

    def list(self, server_id: str) -> tuple[BackupInfo, ...]:
        """Return the backups of ``server_id``, newest first."""
        return self._store.list_backups(server_id)

    def create(
        self,
        server_id: str,
        note: str = "",
        progress: ProgressReporter | None = None,
        kind: BackupKind = BackupKind.MANUAL,
        cancel: CancelToken | None = None,
    ) -> BackupInfo:
        """Back up ``server_id`` (online if it runs); raise ``BackupNotPossible`` while it starts or stops."""
        directory = self._repository.get(server_id).directory
        archiving = stage_callback(Stage.ARCHIVING, progress, cancel)
        if self._coordinator.active_server_id != server_id:
            return self._store.create_backup(server_id, directory, kind, note, False, self._clock(), archiving)
        if self._coordinator.state is not ServerState.RUNNING:
            raise BackupNotPossible(server_id)
        if cancel is not None:
            cancel.check()
        report(progress, Stage.SAVING_WORLD)
        self._coordinator.send_command(server_id, "save-off")
        try:
            confirmed = self._coordinator.send_and_wait_for_line(
                server_id, "save-all flush", lambda line: "Saved the game" in line, self._save_timeout
            )
            if not confirmed:
                raise BackupFailed(server_id, "the server did not confirm that the world was saved")
            return self._store.create_backup(server_id, directory, kind, note, True, self._clock(), archiving)
        finally:
            try:
                self._coordinator.send_command(server_id, "save-on")
            except Exception:
                _logger.exception("Could not turn world saving back on for %r.", server_id)

    def restore(
        self,
        server_id: str,
        backup_id: str,
        progress: ProgressReporter | None = None,
        cancel: CancelToken | None = None,
    ) -> BackupInfo:
        """Restore ``backup_id`` while the server is stopped; return the safety backup made first."""
        if self._coordinator.active_server_id == server_id:
            raise ServerIsRunning(server_id)
        if not any(backup.backup_id == backup_id for backup in self._store.list_backups(server_id)):
            raise BackupNotFound(server_id, backup_id)
        directory = self._repository.get(server_id).directory
        safety = self._store.create_backup(
            server_id,
            directory,
            BackupKind.SAFETY,
            f"before restoring {backup_id}",
            False,
            self._clock(),
            stage_callback(Stage.SAFETY_BACKUP, progress, cancel),
        )
        # Cancel is honoured while extracting; once the folders are swapped the restore always completes.
        self._store.restore_backup(server_id, directory, backup_id, stage_callback(Stage.EXTRACTING, progress, cancel))
        return safety

    def delete(self, server_id: str, backup_id: str) -> RemovedServerFiles:
        """Move a backup to the Recycle Bin (or trash)."""
        if not any(backup.backup_id == backup_id for backup in self._store.list_backups(server_id)):
            raise BackupNotFound(server_id, backup_id)
        return self._store.delete_backup(server_id, backup_id)

    def recover_interrupted_restores(self) -> tuple[str, ...]:
        """Repair restores cut off by a crash (call once at startup)."""
        try:
            return self._store.recover_interrupted_restores()
        except Exception:
            _logger.exception("Could not check for interrupted restores.")
            return ()
