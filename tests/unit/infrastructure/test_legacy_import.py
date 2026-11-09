"""Tests for importing legacy servers_config.json entries into the new store."""

import json
from pathlib import Path
from typing import Any

import pytest

from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.legacy_import import LegacyServerConfigurationImporter
from mcserver.infrastructure.server_configuration import (
    LegacyServerConfigurationRepository,
    ServerConfigurationError,
)
from mcserver.infrastructure.server_configuration_store import (
    CorruptServerConfigurationFile,
    JsonServerConfigurationRepository,
)

LEGACY_FILE = "servers_config.json"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    servers = tmp_path / "servers"
    servers.mkdir()
    return servers


def legacy_entry(root: Path, name: str, jar: str = "paper.jar", ram: Any = 2048) -> dict[str, Any]:
    """Build an entry exactly as legacy ServerManager.save_servers writes it."""
    directory = root / name
    directory.mkdir(exist_ok=True)
    (directory / jar).write_bytes(b"jar")
    return {"name": name, "core_name": jar, "jar_path": str(directory / jar), "ram": ram, "directory": str(directory)}


def write_legacy(root: Path, entries: dict[str, Any]) -> Path:
    path = root / LEGACY_FILE
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return path


def importer(root: Path) -> tuple[LegacyServerConfigurationImporter, JsonServerConfigurationRepository]:
    target = JsonServerConfigurationRepository(root)
    return LegacyServerConfigurationImporter(LegacyServerConfigurationRepository(root), target), target


def test_imports_legacy_entries_as_relative_configurations(root: Path) -> None:
    legacy_path = write_legacy(
        root,
        {"survival": legacy_entry(root, "survival", ram=4096), "creative": legacy_entry(root, "creative", "f.jar")},
    )
    legacy_before = legacy_path.read_bytes()
    run, target = importer(root)

    report = run.import_all()

    assert report.imported == ("survival", "creative")
    assert report.already_present == ()
    assert report.rejected == ()
    assert target.list_all() == (
        ServerConfiguration("survival", "survival", "paper.jar", 4096),
        ServerConfiguration("creative", "creative", "f.jar", 2048),
    )
    assert legacy_path.read_bytes() == legacy_before


def test_import_is_repeatable_and_never_overwrites_existing_configurations(root: Path) -> None:
    write_legacy(root, {"survival": legacy_entry(root, "survival", ram=4096)})
    run, target = importer(root)
    run.import_all()
    edited = ServerConfiguration("survival", "survival", "paper.jar", 8192)
    target.update(edited)

    report = run.import_all()

    assert report.imported == ()
    assert report.already_present == ("survival",)
    assert target.list_all() == (edited,)


def test_import_clamps_legacy_memory_like_the_legacy_launcher(root: Path) -> None:
    write_legacy(root, {"small": legacy_entry(root, "small", ram=128), "big": legacy_entry(root, "big", ram=10**9)})
    run, target = importer(root)

    run.import_all()

    assert target.get("small").memory_mb == 512
    assert target.get("big").memory_mb == 262144


def test_import_accepts_relative_jar_path_like_legacy_core_name(root: Path) -> None:
    entry = legacy_entry(root, "survival")
    entry["jar_path"] = ""
    write_legacy(root, {"survival": entry})
    run, target = importer(root)

    run.import_all()

    assert target.get("survival").jar_file == "paper.jar"


def test_invalid_legacy_entries_are_rejected_and_valid_ones_still_imported(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    write_legacy(
        root,
        {
            "survival": legacy_entry(root, "survival"),
            "escaped": {"core_name": "paper.jar", "ram": 1024, "directory": str(outside)},
            "no-ram": {**legacy_entry(root, "no-ram"), "ram": "lots"},
            "not-an-object": "survival",
            "CON": {**legacy_entry(root, "survival"), "directory": str(root / "survival")},
        },
    )
    run, target = importer(root)

    report = run.import_all()

    assert report.imported == ("survival",)
    assert [server_id for server_id, _reason in report.rejected] == ["escaped", "no-ram", "not-an-object", "CON"]
    assert all(reason for _server_id, reason in report.rejected)
    assert [configuration.server_id for configuration in target.list_all()] == ["survival"]


def test_legacy_entry_sharing_a_directory_is_rejected(root: Path) -> None:
    first = legacy_entry(root, "survival")
    write_legacy(root, {"survival": first, "copy": dict(first)})
    run, _target = importer(root)

    report = run.import_all()

    assert report.imported == ("survival",)
    assert report.rejected[0][0] == "copy"
    assert "already used" in report.rejected[0][1]


def test_missing_legacy_file_imports_nothing(root: Path) -> None:
    run, target = importer(root)

    report = run.import_all()

    assert report.imported == report.already_present == report.rejected == ()
    assert not target.path.exists()


def test_corrupt_legacy_file_stops_import_without_changes(root: Path) -> None:
    (root / LEGACY_FILE).write_text("{broken", encoding="utf-8")
    run, target = importer(root)

    with pytest.raises(ServerConfigurationError):
        run.import_all()
    assert not target.path.exists()
    assert (root / LEGACY_FILE).read_text(encoding="utf-8") == "{broken"


def test_corrupt_target_store_stops_import_and_is_left_untouched(root: Path) -> None:
    write_legacy(root, {"survival": legacy_entry(root, "survival")})
    run, target = importer(root)
    target.path.write_text("{broken", encoding="utf-8")

    with pytest.raises(CorruptServerConfigurationFile):
        run.import_all()
    assert target.path.read_text(encoding="utf-8") == "{broken"
