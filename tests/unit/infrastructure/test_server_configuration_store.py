"""Tests for the versioned JSON server configuration repository."""

import json
from pathlib import Path
from typing import Any

import pytest

from mcserver.application.errors import (
    ServerConfigurationAlreadyExists,
    ServerConfigurationNotFound,
    ServerConfigurationStorageError,
    ServerDirectoryInUse,
)
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure import server_configuration_store
from mcserver.infrastructure.server_configuration import ServerConfigurationError
from mcserver.infrastructure.server_configuration_store import (
    CONFIGURATION_FILE_NAME,
    CorruptServerConfigurationFile,
    JsonServerConfigurationRepository,
    ServerConfigurationWriteFailed,
    StoredServerLaunchSettings,
    UnsupportedServerConfigurationFormat,
)

SURVIVAL = ServerConfiguration("survival", "survival", "paper.jar", 4096)
CREATIVE = ServerConfiguration("creative", "creative", "fabric.jar", 2048)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    servers = tmp_path / "servers"
    servers.mkdir()
    return servers


@pytest.fixture
def repository(root: Path) -> JsonServerConfigurationRepository:
    return JsonServerConfigurationRepository(root)


def write_raw(root: Path, content: str | bytes) -> Path:
    path = root / CONFIGURATION_FILE_NAME
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def write_document(root: Path, document: Any) -> Path:
    return write_raw(root, json.dumps(document))


def valid_entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "server_id": "survival",
        "directory": "survival",
        "jar_file": "paper.jar",
        "memory_mb": 1024,
    }
    entry.update(overrides)
    return entry


# --- basic operations -----------------------------------------------------


def test_missing_file_means_no_servers_and_is_not_created_by_reads(
    repository: JsonServerConfigurationRepository,
) -> None:
    assert repository.list_all() == ()
    with pytest.raises(ServerConfigurationNotFound):
        repository.get("survival")
    assert not repository.path.exists()


def test_add_persists_versioned_format_with_relative_names(
    root: Path, repository: JsonServerConfigurationRepository
) -> None:
    repository.add(SURVIVAL)

    document = json.loads(repository.path.read_text(encoding="utf-8"))
    assert document == {
        "format_version": 1,
        "servers": [{"server_id": "survival", "directory": "survival", "jar_file": "paper.jar", "memory_mb": 4096}],
    }
    assert str(root) not in repository.path.read_text(encoding="utf-8")


def test_saved_configuration_is_read_by_a_new_repository_instance(root: Path) -> None:
    JsonServerConfigurationRepository(root).add(SURVIVAL)

    assert JsonServerConfigurationRepository(root).get("survival") == SURVIVAL


def test_list_all_returns_servers_in_insertion_order(repository: JsonServerConfigurationRepository) -> None:
    repository.add(SURVIVAL)
    repository.add(CREATIVE)

    assert repository.list_all() == (SURVIVAL, CREATIVE)


def test_update_replaces_only_the_matching_server(repository: JsonServerConfigurationRepository) -> None:
    repository.add(SURVIVAL)
    repository.add(CREATIVE)
    changed = ServerConfiguration("survival", "survival", "purpur.jar", 8192)

    repository.update(changed)

    assert repository.get("survival") == changed
    assert repository.get("creative") == CREATIVE
    assert repository.list_all() == (changed, CREATIVE)


def test_update_unknown_server_raises_not_found(repository: JsonServerConfigurationRepository) -> None:
    with pytest.raises(ServerConfigurationNotFound):
        repository.update(SURVIVAL)


def test_remove_deletes_only_the_matching_server(repository: JsonServerConfigurationRepository) -> None:
    repository.add(SURVIVAL)
    repository.add(CREATIVE)

    repository.remove("survival")

    assert repository.list_all() == (CREATIVE,)
    with pytest.raises(ServerConfigurationNotFound):
        repository.get("survival")


def test_remove_unknown_server_raises_not_found(repository: JsonServerConfigurationRepository) -> None:
    repository.add(SURVIVAL)

    with pytest.raises(ServerConfigurationNotFound):
        repository.remove("creative")
    assert repository.list_all() == (SURVIVAL,)


def test_adding_existing_server_id_is_rejected_without_change(repository: JsonServerConfigurationRepository) -> None:
    repository.add(SURVIVAL)

    with pytest.raises(ServerConfigurationAlreadyExists):
        repository.add(ServerConfiguration("survival", "other", "x.jar", 1024))
    assert repository.list_all() == (SURVIVAL,)


def test_repeated_identical_update_keeps_one_entry(repository: JsonServerConfigurationRepository) -> None:
    repository.add(SURVIVAL)

    repository.update(SURVIVAL)
    repository.update(SURVIVAL)

    assert repository.list_all() == (SURVIVAL,)
    assert len(json.loads(repository.path.read_text(encoding="utf-8"))["servers"]) == 1


def test_server_ids_are_case_sensitive_but_directories_must_be_unique_ignoring_case(
    repository: JsonServerConfigurationRepository,
) -> None:
    repository.add(SURVIVAL)
    repository.add(ServerConfiguration("Survival", "survival-2", "paper.jar", 1024))

    with pytest.raises(ServerDirectoryInUse) as error:
        repository.add(ServerConfiguration("hardcore", "SURVIVAL", "paper.jar", 1024))
    assert error.value.owner_server_id == "survival"
    with pytest.raises(ServerDirectoryInUse):
        repository.update(ServerConfiguration("Survival", "survival", "paper.jar", 1024))
    assert [configuration.server_id for configuration in repository.list_all()] == ["survival", "Survival"]


def test_non_ascii_values_round_trip(root: Path, repository: JsonServerConfigurationRepository) -> None:
    configuration = ServerConfiguration("Виживання", "Виживання", "ядро.jar", 1024)

    repository.add(configuration)

    assert JsonServerConfigurationRepository(root).get("Виживання") == configuration
    assert "Виживання" in repository.path.read_text(encoding="utf-8")


def test_file_with_byte_order_mark_is_readable(root: Path) -> None:
    write_raw(root, b"\xef\xbb\xbf" + json.dumps({"format_version": 1, "servers": [valid_entry()]}).encode())

    assert JsonServerConfigurationRepository(root).get("survival").memory_mb == 1024


def test_first_write_creates_missing_servers_directory(tmp_path: Path) -> None:
    repository = JsonServerConfigurationRepository(tmp_path / "new-root")

    repository.add(SURVIVAL)

    assert repository.get("survival") == SURVIVAL


# --- invalid files ----------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "not valid JSON"),
        (b"\xff\xfe\x00broken", "UTF-8"),
        ("[]", "top level"),
        ('{"servers": []}', "format_version"),
        ('{"format_version": "1", "servers": []}', "format_version"),
        ('{"format_version": true, "servers": []}', "format_version"),
        ('{"format_version": 1}', "'servers'"),
        ('{"format_version": 1, "servers": {}}', "'servers'"),
        ('{"format_version": 1, "servers": [], "extra": 1}', "unknown top-level"),
        ('{"format_version": 1, "servers": ["survival"]}', "must be an object"),
    ],
)
def test_corrupt_file_is_reported(root: Path, content: str | bytes, message: str) -> None:
    write_raw(root, content)

    with pytest.raises(CorruptServerConfigurationFile, match=message):
        JsonServerConfigurationRepository(root).list_all()


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"server_id": "survival", "directory": "survival", "jar_file": "paper.jar"}, "missing fields"),
        (valid_entry(state="running"), "unknown fields"),
        (valid_entry(server_id="../escape"), "identifier"),
        (valid_entry(directory="C:\\abs"), "directory"),
        (valid_entry(jar_file="paper.zip"), "JAR"),
        (valid_entry(memory_mb="4096"), "integer"),
        (valid_entry(memory_mb=128), "between"),
        (valid_entry(server_id=7), "identifier"),
    ],
)
def test_invalid_server_fields_are_reported(root: Path, entry: dict[str, Any], message: str) -> None:
    write_document(root, {"format_version": 1, "servers": [entry]})

    with pytest.raises(CorruptServerConfigurationFile, match=message):
        JsonServerConfigurationRepository(root).list_all()


def test_duplicate_server_ids_in_file_are_reported(root: Path) -> None:
    write_document(root, {"format_version": 1, "servers": [valid_entry(), valid_entry(directory="other")]})

    with pytest.raises(CorruptServerConfigurationFile, match="duplicate server_id"):
        JsonServerConfigurationRepository(root).list_all()


def test_shared_directory_in_file_is_reported(root: Path) -> None:
    write_document(root, {"format_version": 1, "servers": [valid_entry(), valid_entry(server_id="copy")]})

    with pytest.raises(CorruptServerConfigurationFile, match="already used"):
        JsonServerConfigurationRepository(root).list_all()


@pytest.mark.parametrize("version", [0, 2, 99])
def test_unknown_format_version_is_reported(root: Path, version: int) -> None:
    write_document(root, {"format_version": version, "servers": []})

    with pytest.raises(UnsupportedServerConfigurationFormat) as error:
        JsonServerConfigurationRepository(root).list_all()
    assert error.value.version == version


@pytest.mark.parametrize(
    "content",
    ["{not json", json.dumps({"format_version": 2, "servers": [], "future": True})],
)
def test_invalid_or_newer_file_is_never_overwritten(root: Path, content: str) -> None:
    path = write_raw(root, content)
    repository = JsonServerConfigurationRepository(root)

    with pytest.raises(ServerConfigurationStorageError):
        repository.add(SURVIVAL)
    with pytest.raises(ServerConfigurationStorageError):
        repository.remove("survival")

    assert path.read_text(encoding="utf-8") == content


def test_storage_errors_share_the_application_base_type() -> None:
    for error_type in (
        CorruptServerConfigurationFile,
        UnsupportedServerConfigurationFormat,
        ServerConfigurationWriteFailed,
    ):
        assert issubclass(error_type, ServerConfigurationStorageError)


# --- failed writes ----------------------------------------------------------


def test_failed_replace_keeps_previous_file_and_leaves_no_temporary_file(
    root: Path, repository: JsonServerConfigurationRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository.add(SURVIVAL)
    before = repository.path.read_bytes()

    def failing_replace(source: object, destination: object) -> None:
        raise PermissionError("file locked by another program")

    monkeypatch.setattr(server_configuration_store.os, "replace", failing_replace)

    with pytest.raises(ServerConfigurationWriteFailed):
        repository.add(CREATIVE)

    assert repository.path.read_bytes() == before
    assert repository.list_all() == (SURVIVAL,)
    assert [path.name for path in root.iterdir()] == [CONFIGURATION_FILE_NAME]


def test_failed_temporary_write_keeps_previous_file(
    root: Path, repository: JsonServerConfigurationRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository.add(SURVIVAL)
    before = repository.path.read_bytes()

    def failing_fsync(_descriptor: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(server_configuration_store.os, "fsync", failing_fsync)

    with pytest.raises(ServerConfigurationWriteFailed):
        repository.update(ServerConfiguration("survival", "survival", "paper.jar", 8192))

    assert repository.path.read_bytes() == before
    assert [path.name for path in root.iterdir()] == [CONFIGURATION_FILE_NAME]


# --- launch settings ----------------------------------------------------------


def test_stored_launch_settings_resolve_paths_against_root(
    root: Path, repository: JsonServerConfigurationRepository
) -> None:
    repository.add(SURVIVAL)

    settings = StoredServerLaunchSettings(repository, root).get_launch_settings("survival")

    assert settings.working_directory == (root / "survival").resolve()
    assert settings.server_jar_path == (root / "survival" / "paper.jar").resolve()
    assert settings.memory_megabytes == 4096


def test_stored_launch_settings_follow_a_moved_servers_root(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    JsonServerConfigurationRepository(old_root).add(SURVIVAL)
    new_root = old_root.rename(tmp_path / "moved")

    settings = StoredServerLaunchSettings(JsonServerConfigurationRepository(new_root), new_root).get_launch_settings(
        "survival"
    )

    assert settings.working_directory == (new_root / "survival").resolve()


def test_stored_launch_settings_reject_directory_resolving_outside_root(
    root: Path, repository: JsonServerConfigurationRepository, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "survival").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links is not permitted in this environment.")
    repository.add(SURVIVAL)

    with pytest.raises(ServerConfigurationError, match="outside"):
        StoredServerLaunchSettings(repository, root).get_launch_settings("survival")


def test_stored_launch_settings_for_unknown_server_raise_not_found(
    root: Path, repository: JsonServerConfigurationRepository
) -> None:
    with pytest.raises(ServerConfigurationNotFound):
        StoredServerLaunchSettings(repository, root).get_launch_settings("missing")
