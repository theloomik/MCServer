"""EULA file handling and session markers on real files (M1-BE-01, M1-BE-08)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcserver.application.errors import UnsafeServerPath
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.server_configuration_store import JsonServerConfigurationRepository
from mcserver.infrastructure.server_files import LocalServerFilesystem, eula_file_accepted
from mcserver.infrastructure.session_markers import MARKER_DIRECTORY, MARKER_FILE, FileSessionMarkerStore


def test_accept_eula_writes_eula_true_atomically(tmp_path: Path) -> None:
    files = LocalServerFilesystem(tmp_path)
    files.create_directory("survival")

    assert not files.eula_accepted("survival")
    files.accept_eula("survival")

    text = (tmp_path / "survival" / "eula.txt").read_text(encoding="utf-8")
    assert "eula=true" in text.splitlines()
    assert files.eula_accepted("survival")
    assert sorted(path.name for path in (tmp_path / "survival").iterdir()) == ["eula.txt"]  # no temp file left


def test_accept_eula_refuses_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(UnsafeServerPath):
        LocalServerFilesystem(tmp_path).accept_eula("missing")


@pytest.mark.parametrize(
    ("content", "accepted"),
    [
        ("eula=true\n", True),
        ("#By changing the setting below to TRUE...\neula = TRUE\n", True),
        ("eula=false\n", False),
        ("# eula=true\n", False),
        ("", False),
    ],
)
def test_eula_file_parsing(tmp_path: Path, content: str, accepted: bool) -> None:
    (tmp_path / "eula.txt").write_text(content, encoding="utf-8")
    assert eula_file_accepted(tmp_path) is accepted


def test_remove_eula_only_removes_that_file(tmp_path: Path) -> None:
    files = LocalServerFilesystem(tmp_path)
    files.create_directory("survival")
    files.accept_eula("survival")
    (tmp_path / "survival" / "level.dat").write_bytes(b"world")

    files.remove_eula("survival")

    assert sorted(path.name for path in (tmp_path / "survival").iterdir()) == ["level.dat"]


def markers_for(tmp_path: Path) -> tuple[FileSessionMarkerStore, JsonServerConfigurationRepository]:
    repository = JsonServerConfigurationRepository(tmp_path)
    repository.add(ServerConfiguration("survival", "survival-files", "paper.jar", 2048))
    (tmp_path / "survival-files").mkdir()
    return FileSessionMarkerStore(tmp_path, repository), repository


def test_marker_is_written_reported_and_cleared(tmp_path: Path) -> None:
    store, _ = markers_for(tmp_path)

    store.write("survival", 1234)

    path = tmp_path / "survival-files" / MARKER_DIRECTORY / MARKER_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["server_id"] == "survival" and data["process_id"] == 1234 and data["started_at"]
    [marker] = store.leftovers()
    assert marker.server_id == "survival" and marker.started_at == data["started_at"]
    store.clear("survival")
    assert store.leftovers() == ()
    assert not path.exists()
    store.clear("survival")  # clearing twice is harmless


def test_unreadable_marker_is_still_reported(tmp_path: Path) -> None:
    store, _ = markers_for(tmp_path)
    path = tmp_path / "survival-files" / MARKER_DIRECTORY / MARKER_FILE
    path.parent.mkdir()
    path.write_text("{not json", encoding="utf-8")

    assert [marker.server_id for marker in store.leftovers()] == ["survival"]


def test_clearing_a_deleted_server_is_ignored(tmp_path: Path) -> None:
    store, repository = markers_for(tmp_path)
    repository.remove("survival")

    store.clear("survival")
