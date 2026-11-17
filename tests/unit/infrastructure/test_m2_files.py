"""Files for M2: config v1 → v2 upgrade, settings file, Recycle Bin removal, folder adoption, launch options."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from mcserver.application.errors import (
    InvalidSourceJar,
    ServerConfigurationAlreadyExists,
    ServerDirectoryAlreadyExists,
    ServerDirectoryInUse,
    ServerFilesRemovalFailed,
)
from mcserver.application.ports import JavaInstallation
from mcserver.application.server_adoption import ServerAdoption
from mcserver.application.settings import ApplicationSettings
from mcserver.bootstrap.server_runtime import build_server_management
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.recycle_bin import TRASH_DIRECTORY, RecycleBinServerFilesRemover
from mcserver.infrastructure.server_configuration import ConfiguredServerRunnerFactory, ServerLaunchSettings
from mcserver.infrastructure.server_configuration_store import JsonServerConfigurationRepository
from mcserver.infrastructure.server_files import write_eula_file
from mcserver.infrastructure.server_folders import LocalServerFolderAdoption
from mcserver.infrastructure.settings_store import SETTINGS_FILE_NAME, JsonApplicationSettingsStore

# --- configuration store v1 → v2 (M2-BE-01, ADR 0007) ---------------------------------------


def test_version_1_file_is_read_and_upgraded_on_the_first_write(tmp_path: Path) -> None:
    v1 = {
        "format_version": 1,
        "servers": [{"server_id": "survival", "directory": "survival", "jar_file": "paper.jar", "memory_mb": 4096}],
    }
    (tmp_path / "server_configurations.json").write_text(json.dumps(v1), encoding="utf-8")
    repository = JsonServerConfigurationRepository(tmp_path)

    assert repository.get("survival") == ServerConfiguration("survival", "survival", "paper.jar", 4096)
    repository.update(ServerConfiguration("survival", "survival", "paper.jar", 4096, display_name="Survival"))

    document = json.loads(repository.path.read_text(encoding="utf-8"))
    assert document["format_version"] == 2
    assert JsonServerConfigurationRepository(tmp_path).get("survival").display_name == "Survival"


def test_version_1_entries_with_v2_fields_are_corrupt(tmp_path: Path) -> None:
    v1 = {
        "format_version": 1,
        "servers": [{"server_id": "s", "directory": "s", "jar_file": "p.jar", "memory_mb": 4096, "display_name": "x"}],
    }
    (tmp_path / "server_configurations.json").write_text(json.dumps(v1), encoding="utf-8")

    with pytest.raises(Exception, match="unknown fields"):
        JsonServerConfigurationRepository(tmp_path).list_all()


def test_all_v2_fields_round_trip(tmp_path: Path) -> None:
    full = ServerConfiguration(
        "survival",
        "survival",
        "paper.jar",
        4096,
        "Survival",
        ("-XX:+UseG1GC",),
        "C:/jdk/bin/java.exe",
        "paper",
        "1.21.11",
    )
    JsonServerConfigurationRepository(tmp_path).add(full)

    assert JsonServerConfigurationRepository(tmp_path).get("survival") == full


# --- settings file (M2-BE-06) --------------------------------------------------------------------


def test_settings_round_trip_and_missing_file_gives_defaults(tmp_path: Path) -> None:
    store = JsonApplicationSettingsStore(tmp_path)
    assert store.load() == ApplicationSettings() and store.load_problem is None

    store.save(ApplicationSettings(language="uk", stop_timeout_seconds=120, legacy_import_offered=True))

    assert JsonApplicationSettingsStore(tmp_path).load() == ApplicationSettings(
        language="uk", stop_timeout_seconds=120, legacy_import_offered=True
    )


def test_damaged_settings_give_defaults_and_are_kept_aside_on_save(tmp_path: Path) -> None:
    (tmp_path / SETTINGS_FILE_NAME).write_text("{not json", encoding="utf-8")
    store = JsonApplicationSettingsStore(tmp_path)

    assert store.load() == ApplicationSettings()
    assert store.load_problem
    store.save(ApplicationSettings(stop_timeout_seconds=100))

    assert list(tmp_path.glob(f"{SETTINGS_FILE_NAME}.corrupt-*"))
    assert JsonApplicationSettingsStore(tmp_path).load().stop_timeout_seconds == 100


def test_legacy_app_settings_file_is_never_touched(tmp_path: Path) -> None:
    (tmp_path / "app_settings.json").write_text('{"language": "uk"}', encoding="utf-8")
    JsonApplicationSettingsStore(tmp_path).save(ApplicationSettings())

    assert (tmp_path / "app_settings.json").read_text(encoding="utf-8") == '{"language": "uk"}'


# --- Recycle Bin removal (M2-BE-03) --------------------------------------------------------------


def server_folder(root: Path, name: str = "survival") -> Path:
    folder = root / name
    (folder / "world").mkdir(parents=True)
    (folder / "world" / "level.dat").write_bytes(b"world")
    return folder


def test_folder_goes_to_the_recycle_bin(tmp_path: Path) -> None:
    folder = server_folder(tmp_path)
    recycled: list[Path] = []

    def recycle(path: Path) -> None:
        recycled.append(path)
        (path / "world" / "level.dat").unlink()
        (path / "world").rmdir()
        path.rmdir()

    result = RecycleBinServerFilesRemover(tmp_path, recycle).remove_server_files("survival")

    assert recycled == [folder] and result.kind == "recycle_bin"


def test_without_recycle_bin_the_folder_is_moved_into_trash(tmp_path: Path) -> None:
    server_folder(tmp_path)

    def no_recycle_bin(_path: Path) -> None:
        raise OSError("no Recycle Bin on this drive")

    result = RecycleBinServerFilesRemover(tmp_path, no_recycle_bin, clock=lambda: 1700000000).remove_server_files(
        "survival"
    )

    target = tmp_path / TRASH_DIRECTORY / "survival-1700000000"
    assert result.kind == "trash" and result.location == str(target)
    assert (target / "world" / "level.dat").read_bytes() == b"world"  # moved, not deleted
    assert not (tmp_path / "survival").exists()


def test_when_both_fail_nothing_is_deleted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server_folder(tmp_path)
    (tmp_path / TRASH_DIRECTORY).write_text("a file blocks the trash folder", encoding="utf-8")

    def no_recycle_bin(_path: Path) -> None:
        raise OSError("no Recycle Bin")

    with pytest.raises(ServerFilesRemovalFailed):
        RecycleBinServerFilesRemover(tmp_path, no_recycle_bin).remove_server_files("survival")

    assert (tmp_path / "survival" / "world" / "level.dat").read_bytes() == b"world"


@pytest.mark.parametrize("name", ["..", ".trash", "a/b"])
def test_only_server_folder_names_are_accepted(tmp_path: Path, name: str) -> None:
    with pytest.raises(ServerFilesRemovalFailed):
        RecycleBinServerFilesRemover(tmp_path, lambda _path: None).remove_server_files(name)


def test_a_missing_folder_is_reported_not_an_error(tmp_path: Path) -> None:
    assert RecycleBinServerFilesRemover(tmp_path, lambda _path: None).remove_server_files("gone").kind == "missing"


# --- folder adoption (M2-BE-04) ------------------------------------------------------------------


def existing_server(base: Path, name: str = "old-server") -> Path:
    folder = base / name
    (folder / "world" / "region").mkdir(parents=True)
    (folder / "world" / "region" / "r.0.0.mca").write_bytes(b"x" * 5000)
    (folder / "plugins").mkdir()
    (folder / "paper.jar").write_bytes(b"jar")
    (folder / "spigot.jar").write_bytes(b"jar")
    (folder / ".mcserver").mkdir()
    (folder / ".mcserver" / "running").write_text("{}", encoding="utf-8")
    write_eula_file(folder, name)
    return folder


def adoption(root: Path) -> tuple[ServerAdoption, LocalServerFolderAdoption]:
    files = LocalServerFolderAdoption(root)
    return ServerAdoption(build_server_management(root), files), files


def test_folder_outside_the_root_is_copied_and_the_source_is_untouched(tmp_path: Path) -> None:
    root = tmp_path / "servers"
    source = existing_server(tmp_path / "elsewhere")
    use_case, _ = adoption(root)
    progress: list[tuple[int, int]] = []

    contents = use_case.inspect(str(source))
    created = use_case.adopt(
        str(source),
        server_id="survival",
        jar_file="paper.jar",
        memory_mb=4096,
        display_name="Old",
        progress=lambda d, t: progress.append((d, t)),
    )

    assert not contents.inside_root and contents.jar_files == ("paper.jar", "spigot.jar") and contents.eula_accepted
    assert created == ServerConfiguration("survival", "survival", "paper.jar", 4096, display_name="Old")
    assert (root / "survival" / "world" / "region" / "r.0.0.mca").read_bytes() == b"x" * 5000
    assert (root / "survival" / "plugins").is_dir()  # empty folders are kept
    assert not (root / "survival" / ".mcserver").exists()  # MCServer's own marker is not copied
    assert (source / "paper.jar").read_bytes() == b"jar" and (source / ".mcserver" / "running").exists()
    assert progress and progress[-1][0] == progress[-1][1]


def test_folder_inside_the_root_is_registered_in_place(tmp_path: Path) -> None:
    root = tmp_path / "servers"
    folder = existing_server(root, "creative")
    use_case, _ = adoption(root)

    created = use_case.adopt(str(folder), server_id="creative-server", jar_file="paper.jar", memory_mb=2048)

    assert created.directory == "creative"
    assert sorted(path.name for path in root.iterdir()) == ["creative", "server_configurations.json"]
    with pytest.raises(ServerDirectoryInUse):
        use_case.adopt(str(folder), server_id="again", jar_file="paper.jar", memory_mb=2048)


def test_jar_must_be_in_the_folder(tmp_path: Path) -> None:
    use_case, _ = adoption(tmp_path / "servers")
    with pytest.raises(InvalidSourceJar):
        use_case.adopt(str(existing_server(tmp_path)), server_id="s", jar_file="missing.jar", memory_mb=2048)


def test_existing_target_is_never_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "servers"
    (root / "survival").mkdir(parents=True)
    (root / "survival" / "keep.txt").write_text("mine", encoding="utf-8")
    use_case, _ = adoption(root)

    with pytest.raises(ServerDirectoryAlreadyExists):
        use_case.adopt(str(existing_server(tmp_path)), server_id="survival", jar_file="paper.jar", memory_mb=2048)

    assert sorted(path.name for path in (root / "survival").iterdir()) == ["keep.txt"]


def test_failed_record_removes_only_the_copy(tmp_path: Path) -> None:
    root = tmp_path / "servers"
    management = build_server_management(root)
    management.create_server(server_id="survival", directory="other", jar_file="paper.jar", memory_mb=2048)
    files = LocalServerFolderAdoption(root)
    source = existing_server(tmp_path)

    with pytest.raises(ServerConfigurationAlreadyExists):
        # The id is taken: the copy into "survival" happens first and is undone.
        ServerAdoption(management, files).adopt(str(source), server_id="survival", jar_file="paper.jar", memory_mb=2048)

    assert not (root / "survival").exists()
    assert (source / "world" / "region" / "r.0.0.mca").exists()


# --- launch options from format v2 ---------------------------------------------------------------


class Java:
    def __init__(self) -> None:
        self.inspected: list[str] = []

    def find(self, minimum_major: int | None = None) -> JavaInstallation:
        return JavaInstallation("C:/auto/java.exe", 21, "path")

    def inspect(self, executable: str) -> JavaInstallation:
        self.inspected.append(executable)
        return JavaInstallation(executable, 21, "server")

    def configure(self, executable: str | None) -> JavaInstallation | None:
        return None


def test_jvm_arguments_and_per_server_java_are_used(tmp_path: Path) -> None:
    jar = tmp_path / "server.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("version.json", json.dumps({"id": "1.21.11", "java_version": 21}))
    write_eula_file(tmp_path, "survival")

    class Settings:
        def get_launch_settings(self, server_id: str) -> ServerLaunchSettings:
            return ServerLaunchSettings(server_id, jar, tmp_path, 2048, ("-XX:+UseG1GC",), "C:/jdk21/java.exe")

    java = Java()
    runner = ConfiguredServerRunnerFactory(Settings(), java).create("survival").runner

    assert java.inspected == ["C:/jdk21/java.exe"]
    assert runner.command == ("C:/jdk21/java.exe", "-Xms2048M", "-Xmx2048M", "-XX:+UseG1GC", "-jar", str(jar), "nogui")  # type: ignore[attr-defined]
