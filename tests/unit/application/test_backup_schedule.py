"""Scheduled backups: when they are due, retention and failures (ADR 0008)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mcserver.application.backup_schedule import BackupSchedule, InvalidBackupSchedule, ScheduledBackups
from mcserver.application.backups import BackupFailed, BackupInfo, BackupKind
from mcserver.application.ports import RemovedServerFiles
from mcserver.domain.lifecycle import ServerState
from mcserver.infrastructure.recycle_bin import RecycleBinServerFilesRemover
from mcserver.infrastructure.zip_backup_store import SCHEDULE_FILE_NAME, ZipBackupStore

START = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class Active:
    def __init__(self, server_id: str | None = "survival", state: ServerState = ServerState.RUNNING) -> None:
        self.active_server_id = server_id
        self.state = state


class Schedules:
    def __init__(self, schedule: BackupSchedule) -> None:
        self.items = {"survival": schedule}

    def load_schedule(self, server_id: str) -> BackupSchedule:
        return self.items.get(server_id, BackupSchedule())

    def save_schedule(self, server_id: str, schedule: BackupSchedule) -> None:
        self.items[server_id] = schedule


class Backups:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.items: list[BackupInfo] = []
        self.deleted: list[str] = []
        self.fail = False
        self.created: list[BackupKind] = []

    def list(self, server_id: str) -> tuple[BackupInfo, ...]:
        return tuple(sorted(self.items, key=lambda item: item.created_at, reverse=True))

    def add(self, kind: BackupKind, at: datetime) -> BackupInfo:
        info = BackupInfo(f"{at:%H%M%S}-{kind.value}", "survival", at.isoformat(timespec="seconds"), 10, kind)
        self.items.append(info)
        return info

    def create(self, server_id: str, note: str = "", progress: object = None, kind: BackupKind = BackupKind.MANUAL):
        if self.fail:
            raise BackupFailed(server_id, "the server did not confirm that the world was saved")
        self.created.append(kind)
        return self.add(kind, self.clock())

    def delete(self, server_id: str, backup_id: str) -> RemovedServerFiles:
        self.items = [item for item in self.items if item.backup_id != backup_id]
        self.deleted.append(backup_id)
        return RemovedServerFiles("recycle_bin", backup_id)


def make(schedule: BackupSchedule, active: Active | None = None) -> tuple[ScheduledBackups, Backups, Clock]:
    clock = Clock()
    backups = Backups(clock)
    scheduler = ScheduledBackups(Schedules(schedule), backups, active or Active(), clock)  # type: ignore[arg-type]
    return scheduler, backups, clock


ON = BackupSchedule(enabled=True, interval_hours=2, keep=2)


def test_nothing_is_due_when_the_schedule_is_off_or_the_server_does_not_run() -> None:
    assert make(BackupSchedule())[0].due_server() is None
    assert make(ON, Active(None))[0].due_server() is None
    assert make(ON, Active(state=ServerState.STARTING))[0].due_server() is None
    assert make(ON)[0].due_server() == "survival"  # no backup yet


def test_interval_counts_from_the_newest_backup_of_any_kind() -> None:
    scheduler, backups, clock = make(ON)
    backups.add(BackupKind.MANUAL, START - timedelta(hours=1))
    assert scheduler.due_server() is None
    clock.advance(hours=1)
    assert scheduler.due_server() == "survival"


def test_run_due_makes_a_scheduled_backup_and_keeps_only_the_newest_scheduled_ones() -> None:
    scheduler, backups, clock = make(ON)
    manual = backups.add(BackupKind.MANUAL, START - timedelta(days=30))
    safety = backups.add(BackupKind.SAFETY, START - timedelta(days=20))
    results = []
    for _ in range(4):
        results.append(scheduler.run_due())
        assert scheduler.run_due() is None  # not due again right away
        clock.advance(hours=2)
    assert all(result is not None for result in results)
    remaining = [item.backup_id for item in backups.list("survival")]
    scheduled = [item for item in backups.list("survival") if item.kind is BackupKind.SCHEDULED]
    assert len(scheduled) == 2
    assert manual.backup_id in remaining and safety.backup_id in remaining  # never removed automatically
    assert results[2] is not None and len(results[2].removed) == 1
    assert len(backups.deleted) == 2


def test_failed_backup_is_retried_after_a_pause() -> None:
    scheduler, backups, clock = make(ON)
    backups.fail = True
    with pytest.raises(BackupFailed):
        scheduler.run_due()
    assert scheduler.due_server() is None
    clock.advance(minutes=16)
    assert scheduler.due_server() == "survival"
    backups.fail = False
    assert scheduler.run_due() is not None


def test_saving_a_schedule_clears_the_retry_pause() -> None:
    scheduler, backups, _clock = make(ON)
    backups.fail = True
    with pytest.raises(BackupFailed):
        scheduler.run_due()
    scheduler.set_schedule("survival", ON)
    assert scheduler.due_server() == "survival"


@pytest.mark.parametrize(
    "values",
    [{"interval_hours": 0}, {"interval_hours": 169}, {"keep": 0}, {"keep": 101}, {"enabled": "yes"}, {"keep": True}],
)
def test_invalid_schedules_are_rejected(values: dict[str, object]) -> None:
    with pytest.raises(InvalidBackupSchedule):
        BackupSchedule(**values)  # type: ignore[arg-type]


# --- stored next to the backups -----------------------------------------------------------------


def no_recycle_bin(_path: Path) -> None:
    raise OSError("tests never touch the real Recycle Bin")


def test_schedule_is_stored_next_to_the_backups_and_not_listed_as_one(tmp_path: Path) -> None:
    store = ZipBackupStore(tmp_path, RecycleBinServerFilesRemover(tmp_path, no_recycle_bin))
    assert store.load_schedule("survival") == BackupSchedule()
    store.save_schedule("survival", ON)
    assert store.load_schedule("survival") == ON
    assert (tmp_path / ".backups" / "survival" / SCHEDULE_FILE_NAME).is_file()
    assert store.list_backups("survival") == ()


def test_damaged_schedule_means_off(tmp_path: Path) -> None:
    store = ZipBackupStore(tmp_path)
    folder = tmp_path / ".backups" / "survival"
    folder.mkdir(parents=True)
    (folder / SCHEDULE_FILE_NAME).write_text('{"enabled": true, "interval_hours": 0, "keep": 3}', encoding="utf-8")
    assert store.load_schedule("survival") == BackupSchedule()
    (folder / SCHEDULE_FILE_NAME).write_text("not json", encoding="utf-8")
    assert store.load_schedule("survival") == BackupSchedule()
