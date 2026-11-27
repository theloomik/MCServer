"""Tests for the one-step server creation workflow, using in-memory fakes only."""

import pytest

from mcserver.application.errors import (
    InvalidSourceJar,
    ProvisioningRollbackFailed,
    ServerConfigurationAlreadyExists,
    ServerConfigurationNotFound,
    ServerConfigurationStorageError,
    ServerCreationRollbackFailed,
    ServerDirectoryAlreadyExists,
    ServerDirectoryInUse,
    ServerFilesystemError,
    ServerJarAlreadyExists,
    ServerProvisioningError,
)
from mcserver.application.server_creation import ServerCreation
from mcserver.application.server_management import ServerManagement
from mcserver.application.server_provisioning import ProvisionedServer, ServerProvisioning
from mcserver.domain.errors import InvalidServerConfiguration
from mcserver.domain.server_configuration import ServerConfiguration

SOURCE = "C:/Downloads/paper-1.21.jar"
EXISTING = ServerConfiguration("lobby", "lobby", "velocity.jar", 1024)
NEW = ServerConfiguration("survival", "survival", "paper.jar", 4096)


class BrokenStorage(ServerConfigurationStorageError):
    pass


class InMemoryRepository:
    """Repository fake following the port contract; can fail chosen operations."""

    def __init__(self, *configurations: ServerConfiguration) -> None:
        self.items = {configuration.server_id: configuration for configuration in configurations}
        self.calls: list[str] = []
        self.fail_on: set[str] = set()

    def list_all(self) -> tuple[ServerConfiguration, ...]:
        return tuple(self.items.values())

    def get(self, server_id: str) -> ServerConfiguration:
        self.calls.append(f"get:{server_id}")
        if "get" in self.fail_on:
            raise BrokenStorage("configuration file became unreadable")
        try:
            return self.items[server_id]
        except KeyError:
            raise ServerConfigurationNotFound(server_id) from None

    def add(self, configuration: ServerConfiguration) -> None:
        self.calls.append(f"add:{configuration.server_id}")
        if configuration.server_id in self.items:
            raise ServerConfigurationAlreadyExists(configuration.server_id)
        for other in self.items.values():
            if other.directory.casefold() == configuration.directory.casefold():
                raise ServerDirectoryInUse(configuration.directory, other.server_id)
        self.items[configuration.server_id] = configuration

    def update(self, configuration: ServerConfiguration) -> None:
        self.calls.append(f"update:{configuration.server_id}")
        self.items[configuration.server_id] = configuration

    def remove(self, server_id: str) -> None:
        self.calls.append(f"remove:{server_id}")
        if "remove" in self.fail_on:
            raise BrokenStorage("disk full")
        if self.items.pop(server_id, None) is None:
            raise ServerConfigurationNotFound(server_id)


class NoLegacySource:
    def list_server_ids(self) -> tuple[str, ...]:
        return ()

    def read_server(self, server_id: str) -> ServerConfiguration:
        raise AssertionError("not used")


class FakeFilesystem:
    """In-memory file tree for ServerProvisioning; can fail chosen steps."""

    def __init__(self, **existing: dict[str, bytes]) -> None:
        self.tree: dict[str, dict[str, bytes]] = {name: dict(files) for name, files in existing.items()}
        self.calls: list[str] = []
        self.fail_install: ServerProvisioningError | None = None
        self.fail_remove = False
        self.invalid_sources: set[str] = set()

    def check_source_jar(self, source_jar: str) -> None:
        self.calls.append(f"check:{source_jar}")
        if source_jar in self.invalid_sources:
            raise InvalidSourceJar(source_jar, "the file does not exist")

    def create_directory(self, directory: str) -> None:
        self.calls.append(f"create:{directory}")
        if directory in self.tree:
            raise ServerDirectoryAlreadyExists(directory)
        self.tree[directory] = {}

    def install_jar(self, directory: str, jar_file: str, source_jar: str) -> None:
        self.calls.append(f"install:{directory}/{jar_file}")
        if self.fail_install is not None:
            raise self.fail_install
        self.tree[directory][jar_file] = source_jar.encode()

    def remove_created_directory(self, directory: str) -> None:
        self.calls.append(f"remove:{directory}")
        if self.fail_remove:
            raise ServerFilesystemError("directory is in use", leftovers=(directory,))
        if not self.tree.get(directory):
            self.tree.pop(directory, None)


def workflow(repository: InMemoryRepository, filesystem: FakeFilesystem) -> ServerCreation:
    return ServerCreation(
        ServerManagement(repository, NoLegacySource()),
        ServerProvisioning(repository, filesystem),
    )


def create(creation: ServerCreation, source: str = SOURCE) -> ProvisionedServer:
    return creation.create_server(
        server_id="survival", directory="survival", jar_file="paper.jar", memory_mb=4096, source_jar=source
    )


# --- success ----------------------------------------------------------------------


def test_creates_configuration_then_provisions_and_returns_result() -> None:
    repository = InMemoryRepository(EXISTING)
    filesystem = FakeFilesystem()

    result = create(workflow(repository, filesystem))

    assert result == ProvisionedServer(configuration=NEW, source_jar=SOURCE)
    assert repository.items == {"lobby": EXISTING, "survival": NEW}
    assert filesystem.tree == {"survival": {"paper.jar": SOURCE.encode()}}
    assert repository.calls == ["add:survival", "get:survival"]
    assert filesystem.calls == [f"check:{SOURCE}", "create:survival", "install:survival/paper.jar"]


# --- failures before anything is stored ----------------------------------------------


def test_duplicate_server_id_is_raised_unchanged_and_nothing_is_provisioned() -> None:
    original = ServerConfiguration("survival", "old-survival", "vanilla.jar", 2048)
    repository = InMemoryRepository(original)
    filesystem = FakeFilesystem(**{"old-survival": {"vanilla.jar": b"user jar"}})

    with pytest.raises(ServerConfigurationAlreadyExists):
        create(workflow(repository, filesystem))

    assert repository.items == {"survival": original}
    assert filesystem.calls == []
    assert filesystem.tree == {"old-survival": {"vanilla.jar": b"user jar"}}
    assert not any(call.startswith("remove:") for call in repository.calls)


def test_directory_used_by_another_configuration_is_raised_and_nothing_is_provisioned() -> None:
    repository = InMemoryRepository(ServerConfiguration("other", "survival", "x.jar", 1024))
    filesystem = FakeFilesystem()

    with pytest.raises(ServerDirectoryInUse):
        create(workflow(repository, filesystem))
    assert filesystem.calls == []
    assert list(repository.items) == ["other"]


def test_invalid_values_raise_domain_error_and_store_nothing() -> None:
    repository = InMemoryRepository()
    filesystem = FakeFilesystem()

    with pytest.raises(InvalidServerConfiguration):
        workflow(repository, filesystem).create_server(
            server_id="survival", directory="..", jar_file="paper.jar", memory_mb=4096, source_jar=SOURCE
        )
    assert repository.items == {}
    assert filesystem.calls == []


# --- provisioning failures roll back the new record ----------------------------------


@pytest.mark.parametrize(
    "configure",
    [
        lambda fs: fs.invalid_sources.add(SOURCE),
        lambda fs: setattr(fs, "fail_install", ServerFilesystemError("disk full")),
        lambda fs: setattr(fs, "fail_install", ServerJarAlreadyExists("survival", "paper.jar")),
    ],
    ids=["invalid-source", "copy-failure", "jar-conflict"],
)
def test_provisioning_failure_removes_only_the_new_record_and_reraises(configure: object) -> None:
    repository = InMemoryRepository(EXISTING)
    filesystem = FakeFilesystem()
    assert callable(configure)
    configure(filesystem)

    with pytest.raises(ServerProvisioningError) as error:
        create(workflow(repository, filesystem))

    assert not isinstance(error.value, ServerCreationRollbackFailed)
    assert repository.items == {"lobby": EXISTING}
    assert "remove:survival" in repository.calls
    assert "survival" not in filesystem.tree


def test_original_provisioning_error_object_is_preserved() -> None:
    repository = InMemoryRepository()
    filesystem = FakeFilesystem()
    failure = ServerFilesystemError("disk full")
    filesystem.fail_install = failure

    with pytest.raises(ServerFilesystemError) as error:
        create(workflow(repository, filesystem))
    assert error.value is failure


def test_existing_directory_conflict_rolls_back_record_and_keeps_directory_contents() -> None:
    repository = InMemoryRepository(EXISTING)
    filesystem = FakeFilesystem(survival={"level.dat": b"world", "paper.jar": b"user jar"})

    with pytest.raises(ServerDirectoryAlreadyExists):
        create(workflow(repository, filesystem))

    assert repository.items == {"lobby": EXISTING}
    assert filesystem.tree == {"survival": {"level.dat": b"world", "paper.jar": b"user jar"}}
    assert not any(call.startswith("remove:") for call in filesystem.calls)


def test_provisioning_rollback_failure_still_removes_record_and_keeps_leftovers() -> None:
    repository = InMemoryRepository()
    filesystem = FakeFilesystem()
    filesystem.fail_install = ServerFilesystemError("disk full")
    filesystem.fail_remove = True

    with pytest.raises(ProvisioningRollbackFailed) as error:
        create(workflow(repository, filesystem))

    assert error.value.leftovers == ("survival",)
    assert repository.items == {}


def test_storage_error_while_provisioning_reads_record_triggers_rollback() -> None:
    class FlakyRepository(InMemoryRepository):
        reads = 0

        def get(self, server_id: str) -> ServerConfiguration:
            self.reads += 1
            if self.reads == 1:
                raise BrokenStorage("temporarily unreadable")
            return super().get(server_id)

    repository = FlakyRepository()
    filesystem = FakeFilesystem()

    with pytest.raises(BrokenStorage):
        create(workflow(repository, filesystem))
    assert repository.items == {}
    assert filesystem.calls == []


# --- configuration rollback failures ----------------------------------------------------


def test_record_removal_failure_exposes_both_errors() -> None:
    repository = InMemoryRepository(EXISTING)
    repository.fail_on.add("remove")
    filesystem = FakeFilesystem()
    provisioning_failure = ServerFilesystemError("disk full")
    filesystem.fail_install = provisioning_failure

    with pytest.raises(ServerCreationRollbackFailed) as error:
        create(workflow(repository, filesystem))

    assert error.value.server_id == "survival"
    assert error.value.provisioning_error is provisioning_failure
    assert isinstance(error.value.rollback_error, BrokenStorage)
    assert error.value.__cause__ is error.value.rollback_error
    assert "disk full" in str(error.value)
    assert repository.items == {"lobby": EXISTING, "survival": NEW}


def test_record_changed_by_someone_else_is_kept_and_reported() -> None:
    changed = ServerConfiguration("survival", "survival", "paper.jar", 8192)

    class ConcurrentEditFilesystem(FakeFilesystem):
        def install_jar(self, directory: str, jar_file: str, source_jar: str) -> None:
            repository.items["survival"] = changed  # another caller edits the new record
            raise ServerFilesystemError("disk full")

    repository = InMemoryRepository()
    filesystem = ConcurrentEditFilesystem()

    with pytest.raises(ServerCreationRollbackFailed) as error:
        create(workflow(repository, filesystem))

    assert error.value.rollback_error is None
    assert "changed by another operation" in str(error.value)
    assert repository.items == {"survival": changed}
    assert "remove:survival" not in repository.calls


def test_record_already_removed_by_someone_else_counts_as_rolled_back() -> None:
    class ConcurrentDeleteFilesystem(FakeFilesystem):
        def install_jar(self, directory: str, jar_file: str, source_jar: str) -> None:
            repository.items.pop("survival")
            raise ServerFilesystemError("disk full")

    repository = InMemoryRepository()

    with pytest.raises(ServerFilesystemError):
        create(workflow(repository, ConcurrentDeleteFilesystem()))
    assert repository.items == {}


def test_unreadable_storage_during_rollback_is_reported() -> None:
    repository = InMemoryRepository()
    filesystem = FakeFilesystem()
    filesystem.fail_install = ServerFilesystemError("disk full")

    original_get = repository.get

    def get_then_break(server_id: str) -> ServerConfiguration:
        if any(call.startswith("install:") for call in filesystem.calls):
            raise BrokenStorage("configuration file became unreadable")
        return original_get(server_id)

    repository.get = get_then_break  # type: ignore[method-assign]

    with pytest.raises(ServerCreationRollbackFailed) as error:
        create(workflow(repository, filesystem))
    assert isinstance(error.value.rollback_error, BrokenStorage)
