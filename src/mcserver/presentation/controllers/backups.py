"""List, create, restore and delete the selected server's backups (M3-GUI-04)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import QObject, Qt, Signal

from mcserver.application.backups import BackupInfo, BackupService
from mcserver.application.ports import RemovedServerFiles
from mcserver.presentation.errors import UserMessage, describe_error
from mcserver.presentation.workers import BackgroundRunner


@dataclass(frozen=True, slots=True)
class BackupsState:
    """What the backups view shows."""

    server_id: str | None = None
    backups: tuple[BackupInfo, ...] = ()
    server_active: bool = False
    """The selected server is starting, running or stopping (restore is refused then)."""
    busy: bool = False
    message: UserMessage | None = None
    tone: str = "notice"

    @property
    def can_create(self) -> bool:
        """Return whether a new backup can be started."""
        return self.server_id is not None and not self.busy

    @property
    def can_restore(self) -> bool:
        """Return whether a restore can be started."""
        return self.server_id is not None and not self.busy and not self.server_active


class BackupsController(QObject):
    """Run backup operations in the background; one at a time."""

    state_changed = Signal(object)  # BackupsState
    progress = Signal(int, int)  # bytes done, total bytes

    def __init__(
        self, service: BackupService | None, background: BackgroundRunner, parent: QObject | None = None
    ) -> None:
        """Use ``service`` (``None`` disables backups)."""
        super().__init__(parent)
        self._service = service
        self._background = background
        self._state = BackupsState()
        self._relay = _ProgressRelay(self)
        self._relay.progress.connect(self.progress, Qt.ConnectionType.QueuedConnection)

    @property
    def available(self) -> bool:
        """Return whether backups can be used at all."""
        return self._service is not None

    @property
    def state(self) -> BackupsState:
        """Return the current state."""
        return self._state

    @property
    def busy(self) -> bool:
        """Return whether an operation is running."""
        return self._state.busy

    def show_server(self, server_id: str | None) -> None:
        """Show the backups of ``server_id``."""
        if server_id == self._state.server_id:
            return
        if self._state.busy:
            # The running operation reports into the state of its own server; switching only changes the list.
            self._publish(replace(self._state, server_id=server_id, backups=self._list(server_id), message=None))
            return
        self._publish(BackupsState(server_id=server_id, backups=self._list(server_id), server_active=False))

    def set_active_server(self, active_server_id: str | None) -> None:
        """Track whether the selected server is active (called on every dashboard update)."""
        active = active_server_id is not None and active_server_id == self._state.server_id
        if active != self._state.server_active:
            self._publish(replace(self._state, server_active=active))

    def refresh(self) -> None:
        """Read the list of backups again."""
        self._publish(replace(self._state, backups=self._list(self._state.server_id)))

    def create(self, note: str) -> None:
        """Back up the selected server (online when it runs)."""
        service, server_id = self._service, self._state.server_id
        if service is None or server_id is None or self._state.busy:
            return
        relay = self._relay
        self._start()
        self._background.run(
            lambda: service.create(server_id, note.strip(), relay.report),
            lambda info: self._finish(UserMessage("backups.created", {"backup_id": info.backup_id}), "success"),
            self._fail,
        )

    def restore(self, backup: BackupInfo) -> None:
        """Restore ``backup`` (the service makes a safety backup first)."""
        service = self._service
        if service is None or not self._state.can_restore:
            return
        relay = self._relay
        self._start()
        self._background.run(
            lambda: service.restore(backup.server_id, backup.backup_id, relay.report),
            lambda safety: self._finish(
                UserMessage("backups.restored", {"backup_id": backup.backup_id, "safety_id": safety.backup_id}),
                "success",
            ),
            self._fail,
        )

    def delete(self, backup: BackupInfo) -> None:
        """Move ``backup`` to the Recycle Bin (or the trash folder)."""
        service = self._service
        if service is None or self._state.busy:
            return
        self._start()

        def done(result: RemovedServerFiles) -> None:
            if result.kind == "recycle_bin":
                message = UserMessage("backups.deleted", {"backup_id": backup.backup_id})
            else:
                message = UserMessage(
                    "backups.deleted_trash", {"backup_id": backup.backup_id, "location": result.location}
                )
            self._finish(message, "success")

        self._background.run(lambda: service.delete(backup.server_id, backup.backup_id), done, self._fail)

    def _list(self, server_id: str | None) -> tuple[BackupInfo, ...]:
        if self._service is None or server_id is None:
            return ()
        try:
            return self._service.list(server_id)
        except Exception:
            return ()

    def _start(self) -> None:
        self._publish(replace(self._state, busy=True, message=UserMessage("backups.working"), tone="notice"))

    def _finish(self, message: UserMessage, tone: str) -> None:
        self._publish(
            replace(self._state, busy=False, backups=self._list(self._state.server_id), message=message, tone=tone)
        )

    def _fail(self, error: BaseException) -> None:
        self._finish(describe_error(error), "error")

    def _publish(self, state: BackupsState) -> None:
        self._state = state
        self.state_changed.emit(state)


class _ProgressRelay(QObject):
    """Carries progress from a worker thread to the GUI thread."""

    progress = Signal(int, int)

    def report(self, done: int, total: int) -> None:
        self.progress.emit(done, total)


__all__ = ["BackupsController", "BackupsState"]
