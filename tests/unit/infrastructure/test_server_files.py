"""Tests for the local filesystem provisioning adapter, using temporary directories."""

from pathlib import Path

import pytest

from mcserver.application.errors import (
    InvalidSourceJar,
    ServerDirectoryAlreadyExists,
    ServerFilesystemError,
    ServerJarAlreadyExists,
    UnsafeServerPath,
)
from mcserver.infrastructure import server_files
from mcserver.infrastructure.server_files import LocalServerFilesystem

JAR_BYTES = b"PK\x03\x04 not really a Minecraft server" * 1000


@pytest.fixture
def root(tmp_path: Path) -> Path:
    servers = tmp_path / "servers"
    servers.mkdir()
    return servers


@pytest.fixture
def filesystem(root: Path) -> LocalServerFilesystem:
    return LocalServerFilesystem(root)


@pytest.fixture
def source_jar(tmp_path: Path) -> Path:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    jar = downloads / "paper-1.21.jar"
    jar.write_bytes(JAR_BYTES)
    return jar


def symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError:
        pytest.skip("Creating symbolic links is not permitted in this environment.")


# --- source JAR ------------------------------------------------------------------


def test_accepts_existing_jar_with_any_case_extension(filesystem: LocalServerFilesystem, tmp_path: Path) -> None:
    jar = tmp_path / "Server.JAR"
    jar.write_bytes(b"jar")

    filesystem.check_source_jar(str(jar))


@pytest.mark.parametrize(
    ("make_source", "reason"),
    [
        (lambda tmp: tmp / "missing.jar", "does not exist"),
        (lambda tmp: (tmp / "folder.jar").mkdir() or tmp / "folder.jar", "not a regular file"),
        (lambda tmp: (tmp / "server.zip").write_bytes(b"zip") and tmp / "server.zip", "does not end with .jar"),
        (lambda tmp: tmp / "server", "does not end with .jar"),
    ],
)
def test_rejects_invalid_source(
    filesystem: LocalServerFilesystem, tmp_path: Path, make_source: object, reason: str
) -> None:
    assert callable(make_source)
    source = make_source(tmp_path)

    with pytest.raises(InvalidSourceJar, match=reason):
        filesystem.check_source_jar(str(source))


def test_rejects_empty_source(filesystem: LocalServerFilesystem) -> None:
    with pytest.raises(InvalidSourceJar, match="no file"):
        filesystem.check_source_jar("")


# --- directory creation --------------------------------------------------------------


def test_creates_empty_directory_inside_root(filesystem: LocalServerFilesystem, root: Path) -> None:
    filesystem.create_directory("survival")

    assert (root / "survival").is_dir()
    assert list((root / "survival").iterdir()) == []


def test_creates_missing_servers_root(tmp_path: Path) -> None:
    root = tmp_path / "new-root"

    LocalServerFilesystem(root).create_directory("survival")

    assert (root / "survival").is_dir()


def test_existing_directory_is_a_conflict_and_contents_stay(filesystem: LocalServerFilesystem, root: Path) -> None:
    (root / "survival").mkdir()
    (root / "survival" / "level.dat").write_bytes(b"world")

    with pytest.raises(ServerDirectoryAlreadyExists):
        filesystem.create_directory("survival")
    assert (root / "survival" / "level.dat").read_bytes() == b"world"


def test_existing_file_with_directory_name_is_a_conflict(filesystem: LocalServerFilesystem, root: Path) -> None:
    (root / "survival").write_bytes(b"not a folder")

    with pytest.raises(ServerDirectoryAlreadyExists):
        filesystem.create_directory("survival")
    assert (root / "survival").read_bytes() == b"not a folder"


@pytest.mark.parametrize("name", ["..", ".", "../outside", "a/b", "a\\b", "C:\\servers\\x", "/etc", "", "CON", "x."])
def test_rejects_unsafe_directory_names(filesystem: LocalServerFilesystem, root: Path, name: str) -> None:
    with pytest.raises(UnsafeServerPath):
        filesystem.create_directory(name)
    assert list(root.iterdir()) == []


def test_symlinked_directory_name_is_a_conflict_and_nothing_is_written_outside(
    filesystem: LocalServerFilesystem, root: Path, tmp_path: Path, source_jar: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    symlink_or_skip(root / "survival", outside)

    with pytest.raises(ServerDirectoryAlreadyExists):
        filesystem.create_directory("survival")
    with pytest.raises(UnsafeServerPath, match="symbolic link"):
        filesystem.install_jar("survival", "paper.jar", str(source_jar))
    assert list(outside.iterdir()) == []


def test_dangling_symlink_with_directory_name_is_a_conflict(
    filesystem: LocalServerFilesystem, root: Path, tmp_path: Path
) -> None:
    symlink_or_skip(root / "survival", tmp_path / "does-not-exist")

    with pytest.raises(ServerDirectoryAlreadyExists):
        filesystem.create_directory("survival")
    assert not (tmp_path / "does-not-exist").exists()


def test_directory_creation_os_error_is_reported(
    filesystem: LocalServerFilesystem, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_mkdir = Path.mkdir

    def denied(self: Path, *args: object, **kwargs: object) -> None:
        if self.name == "survival":
            raise PermissionError("Access is denied")
        original_mkdir(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "mkdir", denied)

    with pytest.raises(ServerFilesystemError, match="Access is denied"):
        filesystem.create_directory("survival")
    assert not (root / "survival").exists()


# --- JAR installation ------------------------------------------------------------------


def test_copies_jar_under_configured_name_and_leaves_source_untouched(
    filesystem: LocalServerFilesystem, root: Path, source_jar: Path
) -> None:
    filesystem.create_directory("survival")

    filesystem.install_jar("survival", "paper.jar", str(source_jar))

    assert (root / "survival" / "paper.jar").read_bytes() == JAR_BYTES
    assert source_jar.read_bytes() == JAR_BYTES
    assert sorted(path.name for path in (root / "survival").iterdir()) == ["paper.jar"]


def test_existing_destination_jar_is_never_overwritten(
    filesystem: LocalServerFilesystem, root: Path, source_jar: Path
) -> None:
    (root / "survival").mkdir()
    (root / "survival" / "paper.jar").write_bytes(b"user's own jar")

    with pytest.raises(ServerJarAlreadyExists):
        filesystem.install_jar("survival", "paper.jar", str(source_jar))
    assert (root / "survival" / "paper.jar").read_bytes() == b"user's own jar"


def test_install_rejects_invalid_source(filesystem: LocalServerFilesystem, root: Path, tmp_path: Path) -> None:
    filesystem.create_directory("survival")

    with pytest.raises(InvalidSourceJar):
        filesystem.install_jar("survival", "paper.jar", str(tmp_path / "missing.jar"))
    assert list((root / "survival").iterdir()) == []


@pytest.mark.parametrize("jar_file", ["../paper.jar", "sub/paper.jar", "paper.zip", "/abs.jar", ""])
def test_install_rejects_unsafe_jar_names(
    filesystem: LocalServerFilesystem, root: Path, source_jar: Path, jar_file: str
) -> None:
    filesystem.create_directory("survival")

    with pytest.raises(UnsafeServerPath):
        filesystem.install_jar("survival", jar_file, str(source_jar))
    assert list((root / "survival").iterdir()) == []
    assert sorted(path.name for path in root.iterdir()) == ["survival"]


def test_install_into_missing_directory_is_rejected(filesystem: LocalServerFilesystem, source_jar: Path) -> None:
    with pytest.raises(UnsafeServerPath, match="missing"):
        filesystem.install_jar("survival", "paper.jar", str(source_jar))


def test_failed_copy_removes_partial_jar(
    filesystem: LocalServerFilesystem, root: Path, source_jar: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filesystem.create_directory("survival")

    def disk_full(source: object, destination: object) -> None:
        destination.write(b"half")  # type: ignore[attr-defined]
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(server_files.shutil, "copyfileobj", disk_full)

    with pytest.raises(ServerFilesystemError, match="No space left") as error:
        filesystem.install_jar("survival", "paper.jar", str(source_jar))
    assert error.value.leftovers == ()
    assert list((root / "survival").iterdir()) == []
    assert source_jar.read_bytes() == JAR_BYTES


def test_partial_jar_that_cannot_be_removed_is_reported_as_leftover(
    filesystem: LocalServerFilesystem, root: Path, source_jar: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filesystem.create_directory("survival")

    def disk_full(source: object, destination: object) -> None:
        raise OSError(28, "No space left on device")

    def locked(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("file is locked")

    monkeypatch.setattr(server_files.shutil, "copyfileobj", disk_full)
    monkeypatch.setattr(Path, "unlink", locked)

    with pytest.raises(ServerFilesystemError, match="could not remove the partial file") as error:
        filesystem.install_jar("survival", "paper.jar", str(source_jar))
    assert error.value.leftovers == ("survival/paper.jar",)


def test_unreadable_source_is_reported(
    filesystem: LocalServerFilesystem, root: Path, source_jar: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filesystem.create_directory("survival")
    original_open = Path.open

    def denied(self: Path, mode: str = "r", *args: object, **kwargs: object) -> object:
        if self == source_jar:
            raise PermissionError("Access is denied")
        return original_open(self, mode, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(Path, "open", denied)

    with pytest.raises(ServerFilesystemError, match="Could not read"):
        filesystem.install_jar("survival", "paper.jar", str(source_jar))
    assert list((root / "survival").iterdir()) == []


# --- rollback helper ---------------------------------------------------------------------


def test_remove_created_directory_removes_empty_directory(filesystem: LocalServerFilesystem, root: Path) -> None:
    filesystem.create_directory("survival")

    filesystem.remove_created_directory("survival")

    assert not (root / "survival").exists()


def test_remove_created_directory_never_deletes_contents(filesystem: LocalServerFilesystem, root: Path) -> None:
    (root / "survival").mkdir()
    (root / "survival" / "level.dat").write_bytes(b"world")

    with pytest.raises(ServerFilesystemError) as error:
        filesystem.remove_created_directory("survival")
    assert error.value.leftovers == ("survival",)
    assert (root / "survival" / "level.dat").read_bytes() == b"world"


def test_remove_created_directory_tolerates_missing_directory(filesystem: LocalServerFilesystem) -> None:
    filesystem.remove_created_directory("survival")


def test_remove_created_directory_rejects_unsafe_name(filesystem: LocalServerFilesystem) -> None:
    with pytest.raises(UnsafeServerPath):
        filesystem.remove_created_directory("..")
