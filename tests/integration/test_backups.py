"""Backup safety suite on real files (M3-QA-01, ADR 0008)."""

from __future__ import annotations

import json
import time
import zipfile
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mcserver.application.backup_schedule import BackupSchedule
from mcserver.application.backups import BackupFailed, BackupKind, BackupNotFound, BackupNotPossible
from mcserver.application.errors import ServerIsRunning
from mcserver.bootstrap.server_runtime import ServerRuntime, build_server_runtime
from mcserver.domain.lifecycle import ServerState
from mcserver.infrastructure.recycle_bin import RecycleBinServerFilesRemover
from mcserver.infrastructure.zip_backup_store import BACKUPS_DIRECTORY, ZipBackupStore
from tests.integration.conftest import FakeJavaResolver, use_free_port

WAIT = 10.0


def wait_until(condition: Callable[[], bool], timeout: float = WAIT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def no_recycle_bin(_path: Path) -> None:
    raise OSError("tests never touch the real Recycle Bin")


@pytest.fixture
def runtime(tmp_path: Path, fake_java: Path) -> Iterator[ServerRuntime]:
    with build_server_runtime(
        tmp_path / "servers", FakeJavaResolver(fake_java), startup_timeout=10, stop_timeout=WAIT
    ) as built:
        # Route every "recycle" into the trash folder so tests never use the real Recycle Bin.
        store = ZipBackupStore(tmp_path / "servers", RecycleBinServerFilesRemover(tmp_path / "servers", no_recycle_bin))
        built.backups._store = store  # type: ignore[attr-defined]
        yield built


def make_server(runtime: ServerRuntime, tmp_path: Path, behaviour: str = "normal") -> Path:
    source = tmp_path / "downloads" / "server.jar"
    source.parent.mkdir(exist_ok=True)
    source.write_text(behaviour, encoding="utf-8")
    runtime.server_creation.create_server(
        server_id="survival",
        directory="survival",
        jar_file="server.jar",
        memory_mb=1024,
        source_jar=str(source),
        accept_eula=True,
    )
    folder = tmp_path / "servers" / "survival"
    use_free_port(folder)
    (folder / "world" / "region").mkdir(parents=True)
    (folder / "world" / "level.dat").write_bytes(b"level v1")
    (folder / "world" / "region" / "r.0.0.mca").write_bytes(b"chunks v1" * 1000)
    (folder / "world" / "session.lock").write_bytes(b"lock")
    (folder / "logs").mkdir()
    (folder / "logs" / "latest.log").write_text("log before", encoding="utf-8")
    (folder / "cache").mkdir()
    (folder / "cache" / "mojang.jar").write_bytes(b"big")
    return folder


def test_offline_backup_archives_the_world_without_regenerable_files(runtime: ServerRuntime, tmp_path: Path) -> None:
    make_server(runtime, tmp_path)

    info = runtime.backups.create("survival", "before update")

    assert info.kind is BackupKind.MANUAL and not info.online and info.note == "before update"
    archive = tmp_path / "servers" / BACKUPS_DIRECTORY / "survival" / f"{info.backup_id}.zip"
    with zipfile.ZipFile(archive) as zip_file:
        names = set(zip_file.namelist())
    assert {"world/level.dat", "world/region/r.0.0.mca", "server.jar", "eula.txt"} <= names
    assert not any(
        name.startswith(("logs/", "cache/", ".mcserver/")) or name.endswith("session.lock") for name in names
    )
    assert runtime.backups.list("survival") == (info,)


def test_restore_replaces_the_world_keeps_logs_and_makes_a_safety_backup(
    runtime: ServerRuntime, tmp_path: Path
) -> None:
    folder = make_server(runtime, tmp_path)
    original = runtime.backups.create("survival")
    (folder / "world" / "level.dat").write_bytes(b"griefed")
    (folder / "world" / "new-file").write_bytes(b"added later")
    (folder / "logs" / "latest.log").write_text("log after", encoding="utf-8")

    safety = runtime.backups.restore("survival", original.backup_id)

    assert (folder / "world" / "level.dat").read_bytes() == b"level v1"
    assert not (folder / "world" / "new-file").exists()
    assert (folder / "logs" / "latest.log").read_text(encoding="utf-8") == "log after"  # not part of backups
    assert (folder / "cache" / "mojang.jar").read_bytes() == b"big"
    assert safety.kind is BackupKind.SAFETY
    assert {backup.backup_id for backup in runtime.backups.list("survival")} == {original.backup_id, safety.backup_id}
    # The replaced data was moved aside (here: the trash folder), never deleted.
    trashed = list((tmp_path / "servers" / ".trash").iterdir())
    assert len(trashed) == 1 and (trashed[0] / "world" / "level.dat").read_bytes() == b"griefed"


def test_restore_is_refused_while_the_server_runs(runtime: ServerRuntime, tmp_path: Path) -> None:
    make_server(runtime, tmp_path)
    backup = runtime.backups.create("survival")
    runtime.coordinator.start_server("survival")
    assert wait_until(lambda: runtime.coordinator.state is ServerState.RUNNING)

    with pytest.raises(ServerIsRunning):
        runtime.backups.restore("survival", backup.backup_id)

    assert runtime.coordinator.stop_server() is True


def test_online_backup_pauses_saving_and_resumes_it(runtime: ServerRuntime, tmp_path: Path) -> None:
    make_server(runtime, tmp_path)
    lines: list[str] = []
    runtime.output.subscribe(lambda line: lines.append(line.text))
    runtime.coordinator.start_server("survival")
    assert wait_until(lambda: runtime.coordinator.state is ServerState.RUNNING)

    info = runtime.backups.create("survival")

    assert info.online
    assert runtime.output.flush(WAIT)
    assert wait_until(lambda: "echo: save-on" in lines)
    order = [line for line in lines if line.startswith("echo: save")]
    assert order == ["echo: save-off", "echo: save-all flush", "echo: save-on"]
    assert runtime.coordinator.stop_server() is True


def test_online_backup_fails_cleanly_when_saving_is_not_confirmed(runtime: ServerRuntime, tmp_path: Path) -> None:
    make_server(runtime, tmp_path, "never_saves=1")
    runtime.backups._save_timeout = 0.5  # type: ignore[attr-defined]
    lines: list[str] = []
    runtime.output.subscribe(lambda line: lines.append(line.text))
    runtime.coordinator.start_server("survival")
    assert wait_until(lambda: runtime.coordinator.state is ServerState.RUNNING)

    with pytest.raises(BackupFailed):
        runtime.backups.create("survival")

    assert wait_until(lambda: "echo: save-on" in lines)  # saving is turned back on
    assert runtime.backups.list("survival") == ()
    assert runtime.coordinator.stop_server() is True


def test_no_backup_while_starting(runtime: ServerRuntime, tmp_path: Path) -> None:
    make_server(runtime, tmp_path, "never_ready=1")
    runtime.coordinator.start_server("survival")

    with pytest.raises(BackupNotPossible):
        runtime.backups.create("survival")

    assert runtime.coordinator.stop_server() is True


def test_corrupt_archive_is_rejected_and_the_original_world_is_untouched(
    runtime: ServerRuntime, tmp_path: Path
) -> None:
    folder = make_server(runtime, tmp_path)
    backup = runtime.backups.create("survival")
    archive = tmp_path / "servers" / BACKUPS_DIRECTORY / "survival" / f"{backup.backup_id}.zip"
    with zipfile.ZipFile(archive) as zip_file:
        member = zip_file.getinfo("world/region/r.0.0.mca")
    data = bytearray(archive.read_bytes())
    offset = member.header_offset
    name_length = int.from_bytes(data[offset + 26 : offset + 28], "little")
    extra_length = int.from_bytes(data[offset + 28 : offset + 30], "little")
    data[offset + 30 + name_length + extra_length + 2] ^= 0xFF  # damage that file's compressed bytes
    archive.write_bytes(bytes(data))
    (folder / "world" / "level.dat").write_bytes(b"current")

    with pytest.raises(BackupFailed):
        runtime.backups.restore("survival", backup.backup_id)

    assert (folder / "world" / "level.dat").read_bytes() == b"current"
    assert not list((tmp_path / "servers").glob(".restore-*"))


def test_archive_with_escaping_paths_is_refused(runtime: ServerRuntime, tmp_path: Path) -> None:
    folder = make_server(runtime, tmp_path)
    backup = runtime.backups.create("survival")
    archive = tmp_path / "servers" / BACKUPS_DIRECTORY / "survival" / f"{backup.backup_id}.zip"
    with zipfile.ZipFile(archive, "a") as zip_file:
        zip_file.writestr("../evil.txt", "outside")

    with pytest.raises(BackupFailed):
        runtime.backups.restore("survival", backup.backup_id)

    assert not (tmp_path / "servers" / "evil.txt").exists()
    assert (folder / "world" / "level.dat").read_bytes() == b"level v1"


def test_crash_before_the_swap_puts_the_original_back(runtime: ServerRuntime, tmp_path: Path) -> None:
    folder = make_server(runtime, tmp_path)
    aside = tmp_path / "servers" / ".restore-old-survival-20261123183000"
    folder.rename(aside)  # what a crash right after "move the current folder aside" leaves
    (tmp_path / "servers" / ".restore-survival-20261123183000").mkdir()

    repaired = runtime.backups.recover_interrupted_restores()

    assert repaired == ("survival",)
    assert (folder / "world" / "level.dat").read_bytes() == b"level v1"
    assert not list((tmp_path / "servers").glob(".restore-*"))


def test_delete_moves_the_backup_away_and_unknown_ids_fail(runtime: ServerRuntime, tmp_path: Path) -> None:
    make_server(runtime, tmp_path)
    backup = runtime.backups.create("survival")

    removed = runtime.backups.delete("survival", backup.backup_id)

    assert removed.kind == "trash"
    assert runtime.backups.list("survival") == ()
    with pytest.raises(BackupNotFound):
        runtime.backups.delete("survival", backup.backup_id)


def test_low_disk_space_is_reported_before_writing(
    runtime: ServerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_server(runtime, tmp_path)

    class Usage:
        free = 1024

    monkeypatch.setattr("mcserver.infrastructure.zip_backup_store.shutil.disk_usage", lambda _path: Usage)

    with pytest.raises(BackupFailed, match="disk space"):
        runtime.backups.create("survival")
    assert not list((tmp_path / "servers" / BACKUPS_DIRECTORY / "survival").iterdir())


def test_metadata_is_versioned_and_ids_are_unique(tmp_path: Path) -> None:
    root = tmp_path / "servers"
    folder = root / "survival"
    folder.mkdir(parents=True)
    (folder / "level.dat").write_bytes(b"x")
    store = ZipBackupStore(root, RecycleBinServerFilesRemover(root, no_recycle_bin))
    moment = datetime(2026, 11, 23, 18, 30, tzinfo=timezone.utc)

    first = store.create_backup("survival", "survival", BackupKind.MANUAL, "", False, moment, None)
    second = store.create_backup("survival", "survival", BackupKind.MANUAL, "", False, moment, None)

    assert first.backup_id == "20261123-183000-manual" and second.backup_id == "20261123-183000-manual-2"
    data = json.loads((root / BACKUPS_DIRECTORY / "survival" / f"{first.backup_id}.json").read_text(encoding="utf-8"))
    assert data["format_version"] == 1 and data["directory"] == "survival"


def test_scheduled_backup_runs_online_and_keeps_only_the_newest(runtime: ServerRuntime, tmp_path: Path) -> None:
    make_server(runtime, tmp_path)
    manual = runtime.backups.create("survival", "keep me")
    scheduler = runtime.scheduled_backups
    scheduler.set_schedule("survival", BackupSchedule(enabled=True, interval_hours=1, keep=1))
    assert scheduler.due_server() is None  # stopped servers are not backed up on a schedule

    runtime.coordinator.start_server("survival")
    assert wait_until(lambda: runtime.coordinator.state is ServerState.RUNNING)
    assert scheduler.due_server() is None  # the manual backup is newer than the interval
    for _ in range(2):
        scheduler._clock = lambda: datetime.now(timezone.utc) + timedelta(hours=3)  # type: ignore[attr-defined]
        result = scheduler.run_due()
        assert result is not None and result.backup.online and result.backup.kind is BackupKind.SCHEDULED
        time.sleep(1.1)  # backup ids have one-second resolution
    assert runtime.coordinator.stop_server() is True

    kinds = sorted(backup.kind.value for backup in runtime.backups.list("survival"))
    assert kinds == ["manual", "scheduled"]
    assert manual.backup_id in [backup.backup_id for backup in runtime.backups.list("survival")]
    assert (tmp_path / "servers" / ".trash").is_dir()  # the old scheduled backup was moved, not deleted
