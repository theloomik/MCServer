"""Tests for the read-only legacy servers_config.json source adapter."""

import json
from pathlib import Path
from typing import Any

import pytest

from mcserver.application.errors import LegacyConfigurationUnavailable, LegacyServerEntryInvalid
from mcserver.domain.errors import InvalidServerConfiguration
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.legacy_import import LegacyFileServerConfigurationSource
from mcserver.infrastructure.server_configuration import LegacyServerConfigurationRepository

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


def source(root: Path) -> LegacyFileServerConfigurationSource:
    return LegacyFileServerConfigurationSource(LegacyServerConfigurationRepository(root))


def test_lists_ids_in_file_order_and_converts_to_relative_configuration(root: Path) -> None:
    path = write_legacy(
        root,
        {"survival": legacy_entry(root, "survival", ram=4096), "creative": legacy_entry(root, "creative", "f.jar")},
    )
    before = path.read_bytes()
    legacy = source(root)

    assert legacy.list_server_ids() == ("survival", "creative")
    assert legacy.read_server("survival") == ServerConfiguration("survival", "survival", "paper.jar", 4096)
    assert legacy.read_server("creative") == ServerConfiguration("creative", "creative", "f.jar", 2048)
    assert path.read_bytes() == before


def test_missing_legacy_file_lists_no_servers(root: Path) -> None:
    assert source(root).list_server_ids() == ()
    assert not (root / LEGACY_FILE).exists()


@pytest.mark.parametrize("content", ["{broken", "[1, 2]"])
def test_unreadable_legacy_file_raises_unavailable(root: Path, content: str) -> None:
    (root / LEGACY_FILE).write_text(content, encoding="utf-8")

    with pytest.raises(LegacyConfigurationUnavailable):
        source(root).list_server_ids()
    assert (root / LEGACY_FILE).read_text(encoding="utf-8") == content


def test_memory_is_clamped_like_the_legacy_launcher(root: Path) -> None:
    write_legacy(root, {"small": legacy_entry(root, "small", ram=128), "big": legacy_entry(root, "big", ram=10**9)})
    legacy = source(root)

    assert legacy.read_server("small").memory_mb == 512
    assert legacy.read_server("big").memory_mb == 262144


def test_relative_core_name_is_accepted_when_jar_path_is_empty(root: Path) -> None:
    entry = legacy_entry(root, "survival")
    entry["jar_path"] = ""
    write_legacy(root, {"survival": entry})

    assert source(root).read_server("survival").jar_file == "paper.jar"


@pytest.mark.parametrize(
    ("server_id", "make_entry"),
    [
        ("no-ram", lambda root, outside: {**legacy_entry(root, "no-ram"), "ram": "lots"}),
        ("escaped", lambda root, outside: {"core_name": "paper.jar", "ram": 1024, "directory": str(outside)}),
        ("not-an-object", lambda root, outside: "survival"),
    ],
)
def test_invalid_legacy_entry_raises_entry_invalid_with_reason(
    root: Path, tmp_path: Path, server_id: str, make_entry: Any
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    write_legacy(root, {server_id: make_entry(root, outside)})

    with pytest.raises(LegacyServerEntryInvalid) as error:
        source(root).read_server(server_id)
    assert error.value.server_id == server_id
    assert error.value.reason


def test_entry_breaking_domain_rules_raises_domain_error(root: Path) -> None:
    write_legacy(root, {"CON": {**legacy_entry(root, "survival")}})

    with pytest.raises(InvalidServerConfiguration):
        source(root).read_server("CON")
