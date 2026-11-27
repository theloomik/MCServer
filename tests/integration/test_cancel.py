"""Cancelling long operations removes what they wrote and leaves the original data alone (M4-BE-02)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from mcserver.application.progress import CancelToken, OperationCancelled, Progress, Stage
from mcserver.bootstrap.server_runtime import ServerRuntime, build_server_runtime
from mcserver.infrastructure.recycle_bin import RecycleBinServerFilesRemover
from mcserver.infrastructure.zip_backup_store import BACKUPS_DIRECTORY, ZipBackupStore
from tests.integration.conftest import FakeJavaResolver
from tests.integration.test_backups import WAIT, make_server, no_recycle_bin
from tests.integration.test_worlds import Setup, make_world
from tests.unit.infrastructure.test_m2_files import adoption, existing_server


def cancel_at(stage: Stage, seen: list[Progress] | None = None) -> tuple[CancelToken, object]:
    """Return a token and a reporter that cancels once ``stage`` reports progress."""
    token = CancelToken()

    def reporter(progress: Progress) -> None:
        if seen is not None:
            seen.append(progress)
        if progress.stage is stage and progress.done > 0:
            token.cancel()

    return token, reporter


@pytest.fixture
def runtime(tmp_path: Path, fake_java: Path) -> Iterator[ServerRuntime]:
    with build_server_runtime(
        tmp_path / "servers", FakeJavaResolver(fake_java), startup_timeout=10, stop_timeout=WAIT
    ) as built:
        store = ZipBackupStore(tmp_path / "servers", RecycleBinServerFilesRemover(tmp_path / "servers", no_recycle_bin))
        built.backups._store = store  # type: ignore[attr-defined]
        yield built


def test_backup_reports_archiving_progress(runtime: ServerRuntime, tmp_path: Path) -> None:
    make_server(runtime, tmp_path)
    seen: list[Progress] = []

    runtime.backups.create("survival", progress=seen.append)

    assert seen and all(report.stage is Stage.ARCHIVING for report in seen)
    assert seen[-1].total > 0 and seen[-1].done == seen[-1].total


def test_cancelled_backup_keeps_no_archive(runtime: ServerRuntime, tmp_path: Path) -> None:
    make_server(runtime, tmp_path)
    token, reporter = cancel_at(Stage.ARCHIVING)

    with pytest.raises(OperationCancelled):
        runtime.backups.create("survival", progress=reporter, cancel=token)  # type: ignore[arg-type]

    assert runtime.backups.list("survival") == ()
    assert not list((tmp_path / "servers" / BACKUPS_DIRECTORY / "survival").glob("*.zip*"))


def test_cancelled_restore_leaves_the_server_folder_untouched(runtime: ServerRuntime, tmp_path: Path) -> None:
    folder = make_server(runtime, tmp_path)
    original = runtime.backups.create("survival")
    (folder / "world" / "level.dat").write_bytes(b"changed after the backup")
    token, reporter = cancel_at(Stage.EXTRACTING)

    with pytest.raises(OperationCancelled):
        runtime.backups.restore("survival", original.backup_id, reporter, token)  # type: ignore[arg-type]

    assert (folder / "world" / "level.dat").read_bytes() == b"changed after the backup"
    assert not list((tmp_path / "servers").glob(".restore-*"))
    # The safety backup made before extracting is kept: it is a complete copy of the current world.
    assert len(runtime.backups.list("survival")) == 2


def test_cancelled_world_import_keeps_no_copy(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    source = tmp_path / "downloads" / "big"
    make_world(source, b"x" * 10)
    for index in range(20):
        (source / "region" / f"r.{index}.0.mca").write_bytes(b"y" * 100)
    token, reporter = cancel_at(Stage.IMPORTING)

    with pytest.raises(OperationCancelled):
        setup.service.import_world("survival", str(source), "big", reporter, token)  # type: ignore[arg-type]

    assert not (setup.server / "big").exists()
    assert not list(setup.server.glob(".world-import-*"))
    assert (source / "level.dat").is_file()  # the source is never touched


def test_cancelled_world_export_keeps_no_file(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    target = tmp_path / "out" / "world.zip"
    target.parent.mkdir()
    token, reporter = cancel_at(Stage.EXPORTING)

    with pytest.raises(OperationCancelled):
        setup.service.export_world("survival", "world", str(target), reporter, token)  # type: ignore[arg-type]

    assert not target.exists() and not target.with_name("world.zip.partial").exists()


def test_cancelled_adoption_removes_the_partial_copy_and_registers_nothing(tmp_path: Path) -> None:
    root = tmp_path / "servers"
    source = existing_server(tmp_path / "elsewhere")
    use_case, _ = adoption(root)
    token, reporter = cancel_at(Stage.COPYING)

    with pytest.raises(OperationCancelled):
        use_case.adopt(
            str(source),
            server_id="survival",
            jar_file="paper.jar",
            memory_mb=2048,
            progress=reporter,  # type: ignore[arg-type]
            cancel=token,
        )

    assert not (root / "survival").exists()
    assert (source / "paper.jar").read_bytes() == b"jar"  # the original folder is untouched


def test_a_token_cancelled_before_starting_stops_at_the_first_check(runtime: ServerRuntime, tmp_path: Path) -> None:
    make_server(runtime, tmp_path)
    token = CancelToken()
    token.cancel()

    with pytest.raises(OperationCancelled):
        runtime.backups.create("survival", cancel=token)

    assert runtime.backups.list("survival") == ()
