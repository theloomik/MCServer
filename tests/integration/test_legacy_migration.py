"""Migration of MCServer 0.9.1 ``servers_config.json`` into the v2 store (M2-QA-01).

The samples mirror the shapes found in real 0.9.1 installations (anonymised):

* packaged builds stored absolute ``directory`` and ``jar_path`` values;
* development runs stored paths relative to the working directory
  (``minecraft_servers\\<name>``), which 0.9.1 itself launched as
  ``<directory>/<core_name>``;
* ``jar_path`` can point to where the JAR was copied from;
* JAR names can contain parentheses (``client(1).jar``) and ``name`` duplicates the key.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mcserver.bootstrap.server_runtime import build_server_management
from mcserver.domain.server_configuration import ServerConfiguration


def write_legacy(root: Path, entries: dict[str, object]) -> bytes:
    root.mkdir(parents=True, exist_ok=True)
    data = json.dumps(entries, indent=4).encode("utf-8")
    (root / "servers_config.json").write_bytes(data)
    return data


def make_server(root: Path, name: str, jar: str) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / jar).write_bytes(b"jar")
    return folder


def test_packaged_install_with_absolute_paths(tmp_path: Path) -> None:
    root = tmp_path / "AppData" / "Local" / "MCServer" / "servers"
    downloads = tmp_path / "Downloads"
    entries = {}
    for name, jar, ram in (
        ("bingo", "fabric-server-mc.26.1.2-loader.0.19.3-launcher.1.1.1.jar", 8192),
        ("121", "client.jar", 2048),
        ("2121212", "client(1).jar", 2048),
    ):
        folder = make_server(root, name, jar)
        entries[name] = {
            "name": name,
            "core_name": jar,
            "jar_path": str(downloads / jar),
            "ram": ram,
            "directory": str(folder),
        }
    before = write_legacy(root, entries)

    result = build_server_management(root).import_legacy_servers()

    assert result.imported == ("bingo", "121", "2121212") and result.rejected == ()
    stored = build_server_management(root).list_servers()
    assert stored[0] == ServerConfiguration(
        "bingo", "bingo", "fabric-server-mc.26.1.2-loader.0.19.3-launcher.1.1.1.jar", 8192
    )
    assert stored[2].jar_file == "client(1).jar"
    assert (root / "servers_config.json").read_bytes() == before  # the legacy file is never changed
    assert json.loads((root / "server_configurations.json").read_text(encoding="utf-8"))["format_version"] == 2


def test_development_install_with_paths_relative_to_the_old_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo" / "minecraft_servers"
    make_server(root, "Survival", "paper-1.21.11-130.jar")
    make_server(root, "sdfghj", "paper-1.21.11-130.jar")
    write_legacy(
        root,
        {
            name: {
                "name": name,
                "core_name": "paper-1.21.11-130.jar",
                "jar_path": os.path.join("minecraft_servers", name, "paper-1.21.11-130.jar"),
                "ram": 3072,
                "directory": os.path.join("minecraft_servers", name),
            }
            for name in ("Survival", "sdfghj")
        },
    )
    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)  # the result must not depend on the current directory

    result = build_server_management(root).import_legacy_servers()

    assert result.imported == ("Survival", "sdfghj") and result.rejected == ()
    assert build_server_management(root).get_server("Survival") == ServerConfiguration(
        "Survival", "Survival", "paper-1.21.11-130.jar", 3072
    )


def test_broken_entries_are_rejected_one_by_one_and_repeating_is_safe(tmp_path: Path) -> None:
    root = tmp_path / "servers"
    good = make_server(root, "good", "paper.jar")
    outside = tmp_path / "outside" / "evil"
    outside.mkdir(parents=True)
    write_legacy(
        root,
        {
            "good": {"core_name": "paper.jar", "ram": 1024, "directory": str(good)},
            "ram-text": {"core_name": "paper.jar", "ram": "lots", "directory": str(root / "ram-text")},
            "no-directory": {"core_name": "paper.jar", "ram": 1024},
            "outside": {"core_name": "paper.jar", "ram": 1024, "directory": str(outside)},
            "escaping-jar": {"core_name": "..\\paper.jar", "ram": 1024, "directory": str(root / "escaping-jar")},
        },
    )

    first = build_server_management(root).import_legacy_servers()
    second = build_server_management(root).import_legacy_servers()

    assert first.imported == ("good",)
    assert {item.server_id for item in first.rejected} == {"ram-text", "no-directory", "outside", "escaping-jar"}
    assert (second.imported_count, second.skipped_count, second.rejected_count) == (0, 1, 4)


def test_pending_legacy_servers_drive_the_one_time_offer(tmp_path: Path) -> None:
    root = tmp_path / "servers"
    folder = make_server(root, "survival", "paper.jar")
    write_legacy(root, {"survival": {"core_name": "paper.jar", "ram": 2048, "directory": str(folder)}})
    management = build_server_management(root)

    assert management.pending_legacy_servers() == ("survival",)
    management.import_legacy_servers()
    assert management.pending_legacy_servers() == ()


def test_unreadable_legacy_file_offers_nothing(tmp_path: Path) -> None:
    root = tmp_path / "servers"
    root.mkdir()
    (root / "servers_config.json").write_text("{damaged", encoding="utf-8")

    from mcserver.application.errors import LegacyConfigurationUnavailable

    with pytest.raises(LegacyConfigurationUnavailable):
        build_server_management(root).pending_legacy_servers()
