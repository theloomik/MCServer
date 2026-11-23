"""Worlds on real files: list, switch, create, import, export and delete (M3-BE-07)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from mcserver.application.errors import ServerIsRunning
from mcserver.application.server_properties import ServerPropertiesService
from mcserver.application.worlds import (
    InvalidWorldName,
    InvalidWorldSource,
    WorldAlreadyExists,
    WorldIsActive,
    WorldNotFound,
    WorldService,
)
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.recycle_bin import RecycleBinServerFilesRemover
from mcserver.infrastructure.server_properties_file import FileServerPropertiesStore
from mcserver.infrastructure.world_folders import LocalWorldStore


class Repository:
    def __init__(self) -> None:
        self.item = ServerConfiguration("survival", "survival", "paper.jar", 2048)

    def get(self, server_id: str) -> ServerConfiguration:
        return self.item


def no_recycle_bin(_path: Path) -> None:
    raise OSError("tests never touch the real Recycle Bin")


def make_world(folder: Path, payload: bytes = b"chunks") -> None:
    (folder / "region").mkdir(parents=True)
    (folder / "level.dat").write_bytes(b"level")
    (folder / "region" / "r.0.0.mca").write_bytes(payload)
    (folder / "session.lock").write_bytes(b"lock")


class Setup:
    def __init__(self, root: Path) -> None:
        self.root = root / "servers"
        self.server = self.root / "survival"
        make_world(self.server / "world")
        make_world(self.server / "world_nether")
        make_world(self.server / "world_the_end")
        make_world(self.server / "creative", b"creative chunks")
        (self.server / "plugins").mkdir()
        (self.server / "server.properties").write_text("level-name=world\nmotd=hi\n", encoding="utf-8")
        self.active: str | None = None
        repository = Repository()
        self.properties = ServerPropertiesService(FileServerPropertiesStore(self.root, repository))  # type: ignore[arg-type]
        self.store = LocalWorldStore(self.root, RecycleBinServerFilesRemover(self.root, no_recycle_bin))
        self.service = WorldService(repository, self.store, self.properties, lambda: self.active)  # type: ignore[arg-type]

    def level(self) -> str:
        return self.properties.load("survival").values["level-name"]


@pytest.fixture
def setup(tmp_path: Path) -> Setup:
    return Setup(tmp_path)


def test_overview_groups_dimension_folders_and_marks_the_current_world(setup: Setup) -> None:
    overview = setup.service.overview("survival")
    assert [world.name for world in overview.worlds] == ["world", "creative"]  # current first
    world = overview.worlds[0]
    assert world.active and world.folders == ("world", "world_nether", "world_the_end")
    assert world.size_bytes == 3 * (len(b"level") + len(b"chunks"))  # session.lock is not counted
    assert overview.level_exists


def test_switching_and_creating_change_only_level_name_while_stopped(setup: Setup) -> None:
    setup.service.use_world("survival", "creative")
    assert setup.level() == "creative"
    assert "motd=hi" in (setup.server / "server.properties").read_text(encoding="utf-8")
    setup.service.create_world("survival", "fresh", "12345")
    assert setup.level() == "fresh"
    assert setup.properties.load("survival").values["level-seed"] == "12345"
    overview = setup.service.overview("survival")
    assert overview.level_name == "fresh" and not overview.level_exists

    with pytest.raises(WorldNotFound):
        setup.service.use_world("survival", "missing")
    with pytest.raises(WorldAlreadyExists):
        setup.service.create_world("survival", "plugins")
    for bad in ("a/b", "x_nether", ".hidden", ""):
        with pytest.raises(InvalidWorldName):
            setup.service.create_world("survival", bad)
    setup.active = "survival"
    with pytest.raises(ServerIsRunning):
        setup.service.use_world("survival", "world")


def test_import_folder_copies_without_session_lock_and_never_moves_the_source(setup: Setup, tmp_path: Path) -> None:
    source = tmp_path / "downloads" / "Skyblock"
    make_world(source / "Skyblock")  # wrapped in a folder of the same name, as many downloads are
    setup.service.import_world("survival", str(source), "skyblock")
    imported = setup.server / "skyblock"
    assert (imported / "level.dat").is_file() and (imported / "region" / "r.0.0.mca").is_file()
    assert not (imported / "session.lock").exists()
    assert (source / "Skyblock" / "level.dat").is_file()
    assert setup.level() == "world"  # importing never switches
    assert not list(setup.server.glob(".world-import-*"))


def test_import_zip_finds_the_world_inside_the_archive(setup: Setup, tmp_path: Path) -> None:
    archive = tmp_path / "map.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("Map v2/level.dat", b"level")
        zip_file.writestr("Map v2/region/r.0.0.mca", b"map")
        zip_file.writestr("readme.txt", b"enjoy")
    setup.service.import_world("survival", str(archive), "map")
    assert (setup.server / "map" / "level.dat").read_bytes() == b"level"
    assert not (setup.server / "map" / "readme.txt").exists()


@pytest.mark.parametrize(
    ("members", "reason"),
    [
        ({"readme.txt": b"x"}, "no level.dat"),
        ({"a/level.dat": b"x", "b/level.dat": b"y"}, "several worlds"),
        ({"../evil/level.dat": b"x"}, "unsafe path"),
    ],
)
def test_bad_archives_are_refused_and_leave_nothing(
    setup: Setup, tmp_path: Path, members: dict[str, bytes], reason: str
) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        for name, data in members.items():
            zip_file.writestr(name, data)
    with pytest.raises(InvalidWorldSource, match=reason):
        setup.service.import_world("survival", str(archive), "bad")
    assert not (setup.server / "bad").exists()
    assert not list(setup.server.glob(".world-import-*"))


def test_import_refuses_a_world_from_this_server_and_existing_names(setup: Setup) -> None:
    with pytest.raises(InvalidWorldSource, match="already inside"):
        setup.service.import_world("survival", str(setup.server / "creative"), "copy")
    with pytest.raises(WorldAlreadyExists):
        setup.service.import_world("survival", str(setup.server / "creative"), "creative")


def test_export_writes_all_dimension_folders(setup: Setup, tmp_path: Path) -> None:
    target = tmp_path / "out" / "world.zip"
    target.parent.mkdir()
    setup.service.export_world("survival", "world", str(target))
    with zipfile.ZipFile(target) as zip_file:
        names = set(zip_file.namelist())
    assert {"world/level.dat", "world_nether/region/r.0.0.mca", "world_the_end/level.dat"} <= names
    assert not any(name.endswith("session.lock") for name in names)
    assert not target.with_name("world.zip.partial").exists()


def test_current_world_is_not_exported_while_running_nor_ever_deleted(setup: Setup, tmp_path: Path) -> None:
    setup.active = "survival"
    with pytest.raises(WorldIsActive):
        setup.service.export_world("survival", "world", str(tmp_path / "w.zip"))
    setup.service.export_world("survival", "creative", str(tmp_path / "c.zip"))  # other worlds are fine
    setup.active = None
    with pytest.raises(WorldIsActive):
        setup.service.delete_world("survival", "world")


def test_delete_moves_every_folder_of_the_world_away(setup: Setup) -> None:
    setup.service.use_world("survival", "creative")
    removed = setup.service.delete_world("survival", "world")
    assert len(removed) == 3 and all(item.kind == "trash" for item in removed)
    assert not (setup.server / "world").exists() and not (setup.server / "world_nether").exists()
    assert len(list((setup.root / ".trash").iterdir())) == 3  # moved, not deleted


def test_suggested_names_avoid_existing_folders(setup: Setup) -> None:
    assert setup.service.suggest_name("survival", "creative") == "creative-2"
    assert setup.service.suggest_name("survival", "My Map (v2)") == "My_Map__v2"
    assert setup.service.suggest_name("survival", "...") == "world-2"
