"""List, create, restore and delete the selected server's backups (M3-GUI-04)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import QObject, Qt, Signal

from mcserver.application.backup_schedule import BackupSchedule, ScheduledBackupResult, ScheduledBackups
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
    schedule: BackupSchedule | None = None
    """The selected server's backup schedule (``None`` when schedules are not available)."""
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
    scheduled_finished = Signal(object)  # UserMessage, for the status bar

    def __init__(
        self,
        service: BackupService | None,
        background: BackgroundRunner,
        parent: QObject | None = None,
        schedules: ScheduledBackups | None = None,
    ) -> None:
        """Use ``service`` (``None`` disables backups) and ``schedules`` for automatic backups."""
        super().__init__(parent)
        self._service = service
        self._schedules = schedules if service is not None else None
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
            self._publish(
                replace(
                    self._state,
                    server_id=server_id,
                    backups=self._list(server_id),
                    schedule=self._load_schedule(server_id),
                    message=None,
                )
            )
            return
        self._publish(
            BackupsState(
                server_id=server_id,
                backups=self._list(server_id),
                server_active=False,
                schedule=self._load_schedule(server_id),
            )
        )

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

    def save_schedule(self, schedule: BackupSchedule) -> None:
        """Store the selected server's schedule."""
        schedules, server_id = self._schedules, self._state.server_id
        if schedules is None or server_id is None:
            return
        try:
            schedules.set_schedule(server_id, schedule)
        except Exception as error:
            self._publish(replace(self._state, message=describe_error(error), tone="error"))
            return
        key = "backups.schedule.saved" if schedule.enabled else "backups.schedule.off"
        self._publish(replace(self._state, schedule=schedule, message=UserMessage(key), tone="success"))

    def run_scheduled(self) -> bool:
        """Start the due scheduled backup in the background; return whether one was started."""
        schedules = self._schedules
        if schedules is None or self._state.busy:
            return False
        try:
            due = schedules.due_server()
        except Exception:
            return False
        if due is None:
            return False
        relay = self._relay
        self._start()
        self._background.run(lambda: schedules.run_due(relay.report), self._scheduled_done, self._scheduled_failed)
        return True

    def _scheduled_done(self, result: ScheduledBackupResult | None) -> None:
        if result is None:
            self._publish(replace(self._state, busy=False, message=None))
            return
        message = UserMessage(
            "backups.scheduled_created",
            {
                "server_id": result.backup.server_id,
                "backup_id": result.backup.backup_id,
                "removed": len(result.removed),
            },
        )
        self._finish(message if result.backup.server_id == self._state.server_id else None, "success")
        self.scheduled_finished.emit(message)

    def _scheduled_failed(self, error: BaseException) -> None:
        message = describe_error(error)
        self._finish(message, "error")
        self.scheduled_finished.emit(message)

    def _load_schedule(self, server_id: str | None) -> BackupSchedule | None:
        if self._schedules is None or server_id is None:
            return None
        try:
            return self._schedules.schedule(server_id)
        except Exception:
            return BackupSchedule()

    def _list(self, server_id: str | None) -> tuple[BackupInfo, ...]:
        if self._service is None or server_id is None:
            return ()
        try:
            return self._service.list(server_id)
        except Exception:
            return ()

    def _start(self) -> None:
        self._publish(replace(self._state, busy=True, message=UserMessage("backups.working"), tone="notice"))

    def _finish(self, message: UserMessage | None, tone: str) -> None:
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
