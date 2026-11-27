"""Tests for the server provisioning use case, using in-memory fakes only."""

import pytest

from mcserver.application.errors import (
    InvalidSourceJar,
    ProvisioningRollbackFailed,
    ServerConfigurationNotFound,
    ServerConfigurationStorageError,
    ServerDirectoryAlreadyExists,
    ServerFilesystemError,
    ServerJarAlreadyExists,
    ServerProvisioningError,
)
from mcserver.application.server_provisioning import ProvisionedServer, ServerProvisioning
from mcserver.domain.server_configuration import ServerConfiguration

SURVIVAL = ServerConfiguration("survival", "survival-files", "paper.jar", 4096)
CREATIVE = ServerConfiguration("creative", "creative", "fabric.jar", 2048)
SOURCE = "C:/Downloads/paper-1.21.jar"


class FakeRepository:
    """Read-only repository fake that fails loudly on any write."""

    def __init__(self, *configurations: ServerConfiguration) -> None:
        self.items = {configuration.server_id: configuration for configuration in configurations}

    def list_all(self) -> tuple[ServerConfiguration, ...]:
        return tuple(self.items.values())

    def get(self, server_id: str) -> ServerConfiguration:
        try:
            return self.items[server_id]
        except KeyError:
            raise ServerConfigurationNotFound(server_id) from None

    def add(self, configuration: ServerConfiguration) -> None:
        raise AssertionError("provisioning must not add configurations")

    def update(self, configuration: ServerConfiguration) -> None:
        raise AssertionError("provisioning must not update configurations")

    def remove(self, server_id: str) -> None:
        raise AssertionError("provisioning must not remove configurations")


class BrokenStorage(ServerConfigurationStorageError):
    pass


class FakeFilesystem:
    """In-memory filesystem: records calls and fails on request."""

    def __init__(self, existing_directories: tuple[str, ...] = ()) -> None:
        self.directories: dict[str, dict[str, str]] = {name: {} for name in existing_directories}
        self.calls: list[str] = []
        self.invalid_sources: set[str] = set()
        self.fail_create: ServerProvisioningError | None = None
        self.fail_install: ServerProvisioningError | None = None
        self.fail_remove: ServerProvisioningError | None = None

    def check_source_jar(self, source_jar: str) -> None:
        self.calls.append(f"check:{source_jar}")
        if source_jar in self.invalid_sources:
            raise InvalidSourceJar(source_jar, "the file does not exist")

    def create_directory(self, directory: str) -> None:
        self.calls.append(f"create:{directory}")
        if self.fail_create is not None:
            raise self.fail_create
        if directory in self.directories:
            raise ServerDirectoryAlreadyExists(directory)
        self.directories[directory] = {}

    def install_jar(self, directory: str, jar_file: str, source_jar: str) -> None:
        self.calls.append(f"install:{directory}/{jar_file}")
        if self.fail_install is not None:
            if self.fail_install.leftovers:
                self.directories[directory][jar_file] = "partial"
            raise self.fail_install
        if jar_file in self.directories[directory]:
            raise ServerJarAlreadyExists(directory, jar_file)
        self.directories[directory][jar_file] = source_jar

    def remove_created_directory(self, directory: str) -> None:
        self.calls.append(f"remove:{directory}")
        if self.fail_remove is not None:
            raise self.fail_remove
        if self.directories.get(directory):
            raise ServerFilesystemError("not empty", leftovers=(directory,))
        self.directories.pop(directory, None)


def provisioning(filesystem: FakeFilesystem, repository: FakeRepository | None = None) -> ServerProvisioning:
    return ServerProvisioning(repository or FakeRepository(SURVIVAL, CREATIVE), filesystem)


# --- success --------------------------------------------------------------------


def test_provision_creates_configured_directory_and_installs_jar_under_configured_name() -> None:
    filesystem = FakeFilesystem()

    result = provisioning(filesystem).provision_server("survival", SOURCE)

    assert result == ProvisionedServer(configuration=SURVIVAL, source_jar=SOURCE)
    assert filesystem.directories == {"survival-files": {"paper.jar": SOURCE}}
    assert filesystem.calls == [f"check:{SOURCE}", "create:survival-files", "install:survival-files/paper.jar"]


def test_provision_never_writes_configurations() -> None:
    repository = FakeRepository(SURVIVAL, CREATIVE)

    provisioning(FakeFilesystem(), repository).provision_server("creative", SOURCE)

    assert repository.items == {"survival": SURVIVAL, "creative": CREATIVE}


# --- failures before anything is created ------------------------------------------


def test_unknown_server_raises_not_found_and_touches_no_files() -> None:
    filesystem = FakeFilesystem()

    with pytest.raises(ServerConfigurationNotFound):
        provisioning(filesystem).provision_server("missing", SOURCE)
    assert filesystem.calls == []


def test_configuration_storage_error_propagates_and_touches_no_files() -> None:
    class FailingRepository(FakeRepository):
        def get(self, server_id: str) -> ServerConfiguration:
            raise BrokenStorage("configuration file is corrupt")

    filesystem = FakeFilesystem()

    with pytest.raises(ServerConfigurationStorageError):
        provisioning(filesystem, FailingRepository()).provision_server("survival", SOURCE)
    assert filesystem.calls == []


def test_invalid_source_jar_is_rejected_before_creating_the_directory() -> None:
    filesystem = FakeFilesystem()
    filesystem.invalid_sources.add(SOURCE)

    with pytest.raises(InvalidSourceJar) as error:
        provisioning(filesystem).provision_server("survival", SOURCE)
    assert error.value.source_jar == SOURCE
    assert filesystem.calls == [f"check:{SOURCE}"]
    assert filesystem.directories == {}


def test_existing_directory_is_a_conflict_and_is_left_untouched() -> None:
    filesystem = FakeFilesystem(existing_directories=("survival-files",))
    filesystem.directories["survival-files"]["world"] = "precious"

    with pytest.raises(ServerDirectoryAlreadyExists):
        provisioning(filesystem).provision_server("survival", SOURCE)
    assert filesystem.directories == {"survival-files": {"world": "precious"}}
    assert "remove:survival-files" not in filesystem.calls


def test_directory_creation_failure_propagates_without_rollback() -> None:
    filesystem = FakeFilesystem()
    filesystem.fail_create = ServerFilesystemError("Access is denied")

    with pytest.raises(ServerFilesystemError, match="Access is denied"):
        provisioning(filesystem).provision_server("survival", SOURCE)
    assert not any(call.startswith(("install:", "remove:")) for call in filesystem.calls)


# --- failures after the directory exists -------------------------------------------


def test_jar_copy_failure_removes_created_directory_and_raises_original_error() -> None:
    filesystem = FakeFilesystem()
    failure = ServerFilesystemError("disk full")
    filesystem.fail_install = failure

    with pytest.raises(ServerFilesystemError) as error:
        provisioning(filesystem).provision_server("survival", SOURCE)

    assert error.value is failure
    assert filesystem.directories == {}
    assert filesystem.calls[-1] == "remove:survival-files"


def test_existing_jar_conflict_rolls_back_the_new_directory() -> None:
    filesystem = FakeFilesystem()
    filesystem.fail_install = ServerJarAlreadyExists("survival-files", "paper.jar")

    with pytest.raises(ServerJarAlreadyExists):
        provisioning(filesystem).provision_server("survival", SOURCE)
    assert filesystem.directories == {}


def test_source_disappearing_during_install_rolls_back() -> None:
    filesystem = FakeFilesystem()
    filesystem.fail_install = InvalidSourceJar(SOURCE, "the file no longer exists")

    with pytest.raises(InvalidSourceJar):
        provisioning(filesystem).provision_server("survival", SOURCE)
    assert filesystem.directories == {}


def test_failed_directory_rollback_reports_original_error_and_leftover() -> None:
    filesystem = FakeFilesystem()
    original = ServerFilesystemError("disk full")
    filesystem.fail_install = original
    filesystem.fail_remove = ServerFilesystemError("in use by another program", leftovers=("survival-files",))

    with pytest.raises(ProvisioningRollbackFailed) as error:
        provisioning(filesystem).provision_server("survival", SOURCE)

    assert error.value.server_id == "survival"
    assert error.value.original is original
    assert error.value.leftovers == ("survival-files",)
    assert isinstance(error.value.__cause__, ServerFilesystemError)
    assert "survival-files" in str(error.value)


def test_partial_jar_left_by_install_skips_directory_removal_and_reports_both() -> None:
    filesystem = FakeFilesystem()
    original = ServerFilesystemError("copy failed; partial file kept", leftovers=("survival-files/paper.jar",))
    filesystem.fail_install = original

    with pytest.raises(ProvisioningRollbackFailed) as error:
        provisioning(filesystem).provision_server("survival", SOURCE)

    assert error.value.original is original
    assert error.value.leftovers == ("survival-files/paper.jar", "survival-files")
    assert "remove:survival-files" not in filesystem.calls
    assert filesystem.directories == {"survival-files": {"paper.jar": "partial"}}


def test_rollback_failed_is_a_provisioning_error() -> None:
    assert issubclass(ProvisioningRollbackFailed, ServerProvisioningError)
