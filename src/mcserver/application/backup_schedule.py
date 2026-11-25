"""Scheduled backups while a server runs, with retention (ADR 0008)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Protocol

from mcserver.application.backups import BackupInfo, BackupKind, BackupService
from mcserver.application.progress import CancelToken, ProgressReporter
from mcserver.domain.lifecycle import ServerState

_logger = logging.getLogger(__name__)

INTERVAL_HOURS_RANGE = (1, 168)
KEEP_RANGE = (1, 100)
RETRY_AFTER = timedelta(minutes=15)
"""After a failed scheduled backup, wait this long before trying again."""


class InvalidBackupSchedule(ValueError):
    """Raised when a schedule value is outside its allowed range."""


@dataclass(frozen=True, slots=True)
class BackupSchedule:
    """When to back up a server automatically, and how many scheduled backups to keep."""

    enabled: bool = False
    interval_hours: int = 6
    keep: int = 10
    """Only scheduled backups are counted and removed; manual and safety backups are never removed."""

    def __post_init__(self) -> None:
        """Reject values MCServer cannot use."""
        if not isinstance(self.enabled, bool):
            raise InvalidBackupSchedule("enabled must be true or false.")
        for name, value, (low, high) in (
            ("interval", self.interval_hours, INTERVAL_HOURS_RANGE),
            ("number of backups to keep", self.keep, KEEP_RANGE),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise InvalidBackupSchedule(f"The {name} must be between {low} and {high}.")


class BackupScheduleStore(Protocol):
    """Load and save each server's ``BackupSchedule``."""

    def load_schedule(self, server_id: str) -> BackupSchedule:
        """Return the stored schedule, or the default (off) when there is none or it is unreadable."""

    def save_schedule(self, server_id: str, schedule: BackupSchedule) -> None:
        """Store ``schedule`` atomically."""


class ActiveServer(Protocol):
    """What the scheduler needs to know about the active server (the coordinator)."""

    @property
    def active_server_id(self) -> str | None:
        """Return the active server, if any."""

    @property
    def state(self) -> ServerState:
        """Return the active server's state."""


@dataclass(frozen=True, slots=True)
class ScheduledBackupResult:
    """A scheduled backup that was made, and the old scheduled backups moved to the Recycle Bin."""

    backup: BackupInfo
    removed: tuple[str, ...]


def _parse(created_at: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(created_at)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.astimezone()


class ScheduledBackups:
    """Make a scheduled backup of the running server when it is due, then apply retention.

    A backup is due when the server is RUNNING, its schedule is on and its
    newest backup of any kind is at least ``interval_hours`` old (or it has
    none). Stopped servers are not backed up: their world does not change.
    """

    def __init__(
        self,
        schedules: BackupScheduleStore,
        backups: BackupService,
        active: ActiveServer,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Use ``backups`` for archives and ``active`` to find the running server."""
        self._schedules = schedules
        self._backups = backups
        self._active = active
        self._clock = clock
        self._lock = Lock()
        self._failed_at: dict[str, datetime] = {}

    def schedule(self, server_id: str) -> BackupSchedule:
        """Return the schedule of ``server_id``."""
        return self._schedules.load_schedule(server_id)

    def set_schedule(self, server_id: str, schedule: BackupSchedule) -> None:
        """Store a new schedule for ``server_id``."""
        self._schedules.save_schedule(server_id, schedule)
        with self._lock:
            self._failed_at.pop(server_id, None)

    def due_server(self) -> str | None:
        """Return the running server whose scheduled backup is due, if any."""
        server_id = self._active.active_server_id
        if server_id is None or self._active.state is not ServerState.RUNNING:
            return None
        try:
            schedule = self._schedules.load_schedule(server_id)
        except Exception:
            _logger.exception("Could not read the backup schedule of %r.", server_id)
            return None
        if not schedule.enabled:
            return None
        now = self._clock()
        with self._lock:
            failed_at = self._failed_at.get(server_id)
        if failed_at is not None and now - failed_at < RETRY_AFTER:
            return None
        newest = next(
            (moment for backup in self._backups.list(server_id) if (moment := _parse(backup.created_at))), None
        )
        if newest is not None and now - newest < timedelta(hours=schedule.interval_hours):
            return None
        return server_id

    def run_due(
        self, progress: ProgressReporter | None = None, cancel: CancelToken | None = None
    ) -> ScheduledBackupResult | None:
        """Make the due scheduled backup, if any, and remove scheduled backups beyond ``keep``."""
        server_id = self.due_server()
        if server_id is None:
            return None
        schedule = self._schedules.load_schedule(server_id)
        try:
            backup = self._backups.create(server_id, "", progress, BackupKind.SCHEDULED, cancel)
        except Exception:
            with self._lock:
                self._failed_at[server_id] = self._clock()
            raise
        with self._lock:
            self._failed_at.pop(server_id, None)
        return ScheduledBackupResult(backup, self._prune(server_id, schedule.keep))

    def _prune(self, server_id: str, keep: int) -> tuple[str, ...]:
        scheduled = [backup for backup in self._backups.list(server_id) if backup.kind is BackupKind.SCHEDULED]
        removed: list[str] = []
        for backup in scheduled[keep:]:
            try:
                self._backups.delete(server_id, backup.backup_id)
            except Exception:
                _logger.exception("Could not remove the old scheduled backup %s.", backup.backup_id)
                continue
            removed.append(backup.backup_id)
        return tuple(removed)
