"""Tests for server configuration use cases, using in-memory fakes only."""

import pytest

from mcserver.application.errors import (
    LegacyConfigurationUnavailable,
    LegacyServerEntryInvalid,
    ServerConfigurationAlreadyExists,
    ServerConfigurationNotFound,
    ServerConfigurationStorageError,
    ServerDirectoryInUse,
)
from mcserver.application.server_management import LegacyImportResult, RejectedLegacyServer, ServerManagement
from mcserver.domain.errors import InvalidServerConfiguration
from mcserver.domain.server_configuration import ServerConfiguration

SURVIVAL = ServerConfiguration("survival", "survival", "paper.jar", 4096)
CREATIVE = ServerConfiguration("creative", "creative", "fabric.jar", 2048)


class InMemoryRepository:
    """Repository fake that follows the port contract and records every call."""

    def __init__(self, *configurations: ServerConfiguration) -> None:
        self.items: dict[str, ServerConfiguration] = {c.server_id: c for c in configurations}
        self.calls: list[str] = []

    def list_all(self) -> tuple[ServerConfiguration, ...]:
        self.calls.append("list_all")
        return tuple(self.items.values())

    def get(self, server_id: str) -> ServerConfiguration:
        self.calls.append(f"get:{server_id}")
        try:
            return self.items[server_id]
        except KeyError:
            raise ServerConfigurationNotFound(server_id) from None

    def add(self, configuration: ServerConfiguration) -> None:
        self.calls.append(f"add:{configuration.server_id}")
        if configuration.server_id in self.items:
            raise ServerConfigurationAlreadyExists(configuration.server_id)
        self._require_free_directory(configuration)
        self.items[configuration.server_id] = configuration

    def update(self, configuration: ServerConfiguration) -> None:
        self.calls.append(f"update:{configuration.server_id}")
        if configuration.server_id not in self.items:
            raise ServerConfigurationNotFound(configuration.server_id)
        self._require_free_directory(configuration)
        self.items[configuration.server_id] = configuration

    def remove(self, server_id: str) -> None:
        self.calls.append(f"remove:{server_id}")
        if self.items.pop(server_id, None) is None:
            raise ServerConfigurationNotFound(server_id)

    def _require_free_directory(self, configuration: ServerConfiguration) -> None:
        for other in self.items.values():
            same_directory = other.directory.casefold() == configuration.directory.casefold()
            if other.server_id != configuration.server_id and same_directory:
                raise ServerDirectoryInUse(configuration.directory, other.server_id)


class BrokenStorage(ServerConfigurationStorageError):
    pass


class FailingRepository(InMemoryRepository):
    """Every operation fails as if the storage were corrupt or unwritable."""

    def list_all(self) -> tuple[ServerConfiguration, ...]:
        raise BrokenStorage("storage is corrupt")

    def get(self, server_id: str) -> ServerConfiguration:
        raise BrokenStorage("storage is corrupt")

    def add(self, configuration: ServerConfiguration) -> None:
        raise BrokenStorage("disk full")

    def update(self, configuration: ServerConfiguration) -> None:
        raise BrokenStorage("disk full")

    def remove(self, server_id: str) -> None:
        raise BrokenStorage("disk full")


class FakeLegacySource:
    """Legacy source fake: values are configurations or exceptions raised by read_server."""

    def __init__(self, entries: dict[str, ServerConfiguration | Exception] | None = None) -> None:
        self.entries = entries or {}
        self.unavailable = False

    def list_server_ids(self) -> tuple[str, ...]:
        if self.unavailable:
            raise LegacyConfigurationUnavailable("servers_config.json is not valid JSON")
        return tuple(self.entries)

    def read_server(self, server_id: str) -> ServerConfiguration:
        entry = self.entries[server_id]
        if isinstance(entry, Exception):
            raise entry
        return entry


def management(
    repository: InMemoryRepository | None = None, legacy: FakeLegacySource | None = None
) -> ServerManagement:
    return ServerManagement(repository or InMemoryRepository(), legacy or FakeLegacySource())


# --- list / get ---------------------------------------------------------------


def test_list_servers_returns_repository_order() -> None:
    assert management(InMemoryRepository(SURVIVAL, CREATIVE)).list_servers() == (SURVIVAL, CREATIVE)


def test_list_servers_on_empty_repository_is_empty_tuple() -> None:
    assert management().list_servers() == ()


def test_get_server_returns_configuration() -> None:
    assert management(InMemoryRepository(SURVIVAL)).get_server("survival") == SURVIVAL


def test_get_unknown_server_raises_not_found() -> None:
    with pytest.raises(ServerConfigurationNotFound) as error:
        management().get_server("missing")
    assert error.value.server_id == "missing"


# --- create -------------------------------------------------------------------


def test_create_server_stores_and_returns_domain_configuration() -> None:
    repository = InMemoryRepository()

    created = management(repository).create_server(
        server_id="creative", directory="creative", jar_file="paper.jar", memory_mb=4096
    )

    assert created == ServerConfiguration("creative", "creative", "paper.jar", 4096)
    assert repository.items == {"creative": created}


def test_create_duplicate_server_id_is_rejected_without_overwrite() -> None:
    repository = InMemoryRepository(SURVIVAL)

    with pytest.raises(ServerConfigurationAlreadyExists):
        management(repository).create_server(server_id="survival", directory="other", jar_file="x.jar", memory_mb=1024)
    assert repository.items == {"survival": SURVIVAL}


def test_create_with_directory_of_another_server_is_rejected() -> None:
    repository = InMemoryRepository(SURVIVAL)

    with pytest.raises(ServerDirectoryInUse) as error:
        management(repository).create_server(
            server_id="hardcore", directory="Survival", jar_file="paper.jar", memory_mb=1024
        )
    assert error.value.owner_server_id == "survival"
    assert list(repository.items) == ["survival"]


@pytest.mark.parametrize(
    "values",
    [
        {"server_id": "a/b", "directory": "a", "jar_file": "a.jar", "memory_mb": 1024},
        {"server_id": "a", "directory": "..", "jar_file": "a.jar", "memory_mb": 1024},
        {"server_id": "a", "directory": "a", "jar_file": "a.zip", "memory_mb": 1024},
        {"server_id": "a", "directory": "a", "jar_file": "a.jar", "memory_mb": 64},
    ],
)
def test_create_with_invalid_values_raises_domain_error_and_stores_nothing(values: dict[str, object]) -> None:
    repository = InMemoryRepository()

    with pytest.raises(InvalidServerConfiguration):
        management(repository).create_server(**values)  # type: ignore[arg-type]
    assert repository.items == {}
    assert repository.calls == []


# --- update -------------------------------------------------------------------


def test_update_changes_given_fields_and_keeps_the_rest() -> None:
    repository = InMemoryRepository(SURVIVAL, CREATIVE)

    updated = management(repository).update_server("creative", jar_file="purpur.jar", memory_mb=6144)

    assert updated == ServerConfiguration("creative", "creative", "purpur.jar", 6144)
    assert repository.items["creative"] == updated
    assert repository.items["survival"] == SURVIVAL
    assert list(repository.items) == ["survival", "creative"]


def test_update_can_repoint_directory() -> None:
    repository = InMemoryRepository(SURVIVAL)

    updated = management(repository).update_server("survival", directory="survival-old")

    assert updated.directory == "survival-old"
    assert updated.server_id == "survival"


def test_update_without_changes_returns_current_configuration() -> None:
    assert management(InMemoryRepository(SURVIVAL)).update_server("survival") == SURVIVAL


def test_update_unknown_server_raises_not_found_and_creates_nothing() -> None:
    repository = InMemoryRepository()

    with pytest.raises(ServerConfigurationNotFound):
        management(repository).update_server("missing", memory_mb=2048)
    assert repository.items == {}


def test_update_to_directory_of_another_server_is_rejected() -> None:
    repository = InMemoryRepository(SURVIVAL, CREATIVE)

    with pytest.raises(ServerDirectoryInUse):
        management(repository).update_server("creative", directory="SURVIVAL")
    assert repository.items["creative"] == CREATIVE


def test_update_with_invalid_value_raises_domain_error_and_keeps_stored_value() -> None:
    repository = InMemoryRepository(SURVIVAL)

    with pytest.raises(InvalidServerConfiguration):
        management(repository).update_server("survival", memory_mb=10)
    assert repository.items["survival"] == SURVIVAL
    assert "update:survival" not in repository.calls


# --- delete -------------------------------------------------------------------


def test_delete_removes_only_the_configuration_record() -> None:
    repository = InMemoryRepository(SURVIVAL, CREATIVE)

    result = management(repository).delete_server("survival")

    assert result is None
    assert list(repository.items) == ["creative"]
    # The only side effect is the repository record removal; no file operation exists here.
    assert repository.calls == ["remove:survival"]


def test_delete_unknown_server_raises_not_found() -> None:
    repository = InMemoryRepository(SURVIVAL)

    with pytest.raises(ServerConfigurationNotFound):
        management(repository).delete_server("missing")
    assert list(repository.items) == ["survival"]


# --- storage errors -------------------------------------------------------------


@pytest.mark.parametrize(
    "operation",
    [
        lambda m: m.list_servers(),
        lambda m: m.get_server("survival"),
        lambda m: m.create_server(server_id="a", directory="a", jar_file="a.jar", memory_mb=1024),
        lambda m: m.update_server("survival", memory_mb=2048),
        lambda m: m.delete_server("survival"),
        lambda m: m.import_legacy_servers(),
    ],
)
def test_storage_errors_propagate_with_their_application_type(operation: object) -> None:
    use_cases = management(FailingRepository(), FakeLegacySource({"survival": SURVIVAL}))

    assert callable(operation)
    with pytest.raises(ServerConfigurationStorageError):
        operation(use_cases)


# --- legacy import ----------------------------------------------------------------


def test_import_adds_all_valid_legacy_servers_with_statistics() -> None:
    repository = InMemoryRepository()
    legacy = FakeLegacySource({"survival": SURVIVAL, "creative": CREATIVE})

    result = management(repository, legacy).import_legacy_servers()

    assert result == LegacyImportResult(imported=("survival", "creative"), skipped=(), rejected=())
    assert (result.imported_count, result.skipped_count, result.rejected_count) == (2, 0, 0)
    assert repository.list_all() == (SURVIVAL, CREATIVE)


def test_repeated_import_skips_existing_and_never_overwrites() -> None:
    repository = InMemoryRepository()
    legacy = FakeLegacySource({"survival": SURVIVAL})
    use_cases = management(repository, legacy)
    use_cases.import_legacy_servers()
    edited = use_cases.update_server("survival", memory_mb=8192)

    result = use_cases.import_legacy_servers()

    assert result.imported == ()
    assert result.skipped == ("survival",)
    assert repository.items["survival"] == edited


def test_partially_invalid_import_keeps_going_and_reports_each_problem() -> None:
    repository = InMemoryRepository(SURVIVAL)
    legacy = FakeLegacySource(
        {
            "survival": SURVIVAL,
            "broken": LegacyServerEntryInvalid("broken", "Server RAM must be an integer."),
            "creative": CREATIVE,
            "CON": InvalidServerConfiguration("Invalid server identifier: 'CON'."),
            "copy": ServerConfiguration("copy", "survival", "paper.jar", 1024),
            "hardcore": ServerConfiguration("hardcore", "hardcore", "paper.jar", 1024),
        }
    )

    result = management(repository, legacy).import_legacy_servers()

    assert result.imported == ("creative", "hardcore")
    assert result.skipped == ("survival",)
    assert result.rejected == (
        RejectedLegacyServer("broken", "Server RAM must be an integer."),
        RejectedLegacyServer("CON", "Invalid server identifier: 'CON'."),
        RejectedLegacyServer("copy", "Server directory 'survival' is already used by server 'survival'."),
    )
    assert (result.imported_count, result.skipped_count, result.rejected_count) == (2, 1, 3)
    assert list(repository.items) == ["survival", "creative", "hardcore"]


def test_import_without_legacy_data_reports_nothing() -> None:
    result = management().import_legacy_servers()

    assert result == LegacyImportResult((), (), ())


def test_unreadable_legacy_data_stops_import_before_any_change() -> None:
    repository = InMemoryRepository()
    legacy = FakeLegacySource({"survival": SURVIVAL})
    legacy.unavailable = True

    with pytest.raises(LegacyConfigurationUnavailable):
        management(repository, legacy).import_legacy_servers()
    assert repository.items == {}


def test_import_treats_concurrent_duplicate_as_skipped() -> None:
    class RacingRepository(InMemoryRepository):
        def list_all(self) -> tuple[ServerConfiguration, ...]:
            snapshot = super().list_all()
            self.items.setdefault("survival", SURVIVAL)  # added by someone else after listing
            return snapshot

    result = management(RacingRepository(), FakeLegacySource({"survival": SURVIVAL})).import_legacy_servers()

    assert result.skipped == ("survival",)
    assert result.imported == ()
