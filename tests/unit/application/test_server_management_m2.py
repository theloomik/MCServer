"""M2 management rules: format-v2 fields, edit rules while running, safe delete, settings (M2-BE-01/02/03/06)."""

from __future__ import annotations

import pytest

from mcserver.application.errors import (
    InvalidJavaExecutable,
    ServerConfigurationNotFound,
    ServerFilesRemovalFailed,
    ServerIsRunning,
)
from mcserver.application.ports import JavaInstallation, RemovedServerFiles
from mcserver.application.server_management import ServerManagement
from mcserver.application.settings import ApplicationSettings, InvalidSettings, SettingsService
from mcserver.domain.errors import InvalidServerConfiguration
from mcserver.domain.server_configuration import ServerConfiguration

SURVIVAL = ServerConfiguration("survival", "survival", "paper.jar", 4096)


class Repository:
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
        self.items[configuration.server_id] = configuration

    def update(self, configuration: ServerConfiguration) -> None:
        self.items[configuration.server_id] = configuration

    def remove(self, server_id: str) -> None:
        del self.items[server_id]


class Legacy:
    def __init__(self, *ids: str) -> None:
        self.ids = ids

    def list_server_ids(self) -> tuple[str, ...]:
        return self.ids

    def read_server(self, server_id: str) -> ServerConfiguration:
        raise AssertionError("not used")


class Remover:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.removed: list[str] = []

    def remove_server_files(self, directory: str) -> RemovedServerFiles:
        if self.error is not None:
            raise self.error
        self.removed.append(directory)
        return RemovedServerFiles("recycle_bin", f"C:/servers/{directory}")


def management(
    active: str | None = None, remover: Remover | None = None, *legacy: str
) -> tuple[ServerManagement, Repository]:
    repository = Repository(SURVIVAL)
    return ServerManagement(
        repository, Legacy(*legacy), active_server=lambda: active, files_remover=remover
    ), repository


# --- configuration v2 (M2-BE-01) -----------------------------------------------------------


def test_new_fields_default_to_empty_and_name_falls_back_to_the_id() -> None:
    assert SURVIVAL.name == "survival"
    named = ServerConfiguration("survival", "survival", "paper.jar", 4096, display_name="My Survival")
    assert named.name == "My Survival"


@pytest.mark.parametrize(
    "arguments",
    [("-Xmx4G",), ("-Xms1G",), ("-jar",), ("-cp",), ("",), (" -XX:+UseG1GC",), ("a\nb",), tuple("x" * 33)],
)
def test_reserved_or_malformed_java_arguments_are_rejected(arguments: tuple[str, ...]) -> None:
    with pytest.raises(InvalidServerConfiguration):
        ServerConfiguration("survival", "survival", "paper.jar", 4096, jvm_arguments=arguments)


def test_ordinary_java_arguments_are_accepted() -> None:
    configuration = ServerConfiguration(
        "survival", "survival", "paper.jar", 4096, jvm_arguments=("-XX:+UseG1GC", "-Dfile.encoding=UTF-8")
    )
    assert configuration.jvm_arguments == ("-XX:+UseG1GC", "-Dfile.encoding=UTF-8")


@pytest.mark.parametrize("name", [" padded", "x" * 65, "tab\there"])
def test_invalid_display_names_are_rejected(name: str) -> None:
    with pytest.raises(InvalidServerConfiguration):
        ServerConfiguration("survival", "survival", "paper.jar", 4096, display_name=name)


# --- edit rules (M2-BE-02) ----------------------------------------------------------------------


def test_edit_changes_the_new_fields_and_clears_optional_ones() -> None:
    use_case, repository = management()

    use_case.update_server(
        "survival", display_name="Survival", jvm_arguments=("-XX:+UseG1GC",), java_path="C:/jdk/java.exe"
    )
    updated = use_case.update_server("survival", java_path=None, memory_mb=6144)

    assert updated.display_name == "Survival" and updated.jvm_arguments == ("-XX:+UseG1GC",)
    assert updated.java_path is None and updated.memory_mb == 6144
    assert repository.items["survival"] == updated


def test_moving_folder_or_jar_of_the_running_server_is_refused() -> None:
    use_case, repository = management(active="survival")

    with pytest.raises(ServerIsRunning):
        use_case.update_server("survival", jar_file="purpur.jar")
    with pytest.raises(ServerIsRunning):
        use_case.update_server("survival", directory="other")
    assert repository.items["survival"] == SURVIVAL


def test_other_changes_of_the_running_server_apply_on_next_start() -> None:
    use_case, _ = management(active="survival")

    updated = use_case.update_server("survival", memory_mb=8192, display_name="Live", jar_file="paper.jar")

    assert updated.memory_mb == 8192 and updated.display_name == "Live"


# --- safe delete (M2-BE-03) ---------------------------------------------------------------------


def test_delete_with_files_moves_them_first_then_removes_the_record() -> None:
    remover = Remover()
    use_case, repository = management(remover=remover)

    result = use_case.delete_server("survival", remove_files=True)

    assert remover.removed == ["survival"]
    assert result.files == RemovedServerFiles("recycle_bin", "C:/servers/survival")
    assert repository.items == {}


def test_failed_file_removal_keeps_everything() -> None:
    use_case, repository = management(remover=Remover(ServerFilesRemovalFailed("survival", "locked")))

    with pytest.raises(ServerFilesRemovalFailed):
        use_case.delete_server("survival", remove_files=True)

    assert repository.items == {"survival": SURVIVAL}


def test_the_running_server_cannot_be_deleted() -> None:
    remover = Remover()
    use_case, repository = management(active="survival", remover=remover)

    with pytest.raises(ServerIsRunning):
        use_case.delete_server("survival", remove_files=True)

    assert remover.removed == [] and "survival" in repository.items


def test_pending_legacy_servers_excludes_stored_ones() -> None:
    use_case, _ = management(None, None, "survival", "creative", "lobby")

    assert use_case.pending_legacy_servers() == ("creative", "lobby")


# --- settings (M2-BE-06) ------------------------------------------------------------------------


class SettingsRepository:
    def __init__(self, settings: ApplicationSettings | None = None, problem: str | None = None) -> None:
        self.settings = settings or ApplicationSettings()
        self.load_problem = problem
        self.saved: list[ApplicationSettings] = []

    def load(self) -> ApplicationSettings:
        return self.settings

    def save(self, settings: ApplicationSettings) -> None:
        self.saved.append(settings)


class Java:
    def __init__(self) -> None:
        self.configured: list[str | None] = []

    def configure(self, executable: str | None) -> JavaInstallation | None:
        if executable == "broken.exe":
            raise InvalidJavaExecutable(executable)
        self.configured.append(executable)
        return None


class Timeouts:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []

    def configure_timeouts(self, startup_timeout: float, stop_timeout: float) -> None:
        self.calls.append((startup_timeout, stop_timeout))


def test_apply_configures_java_and_timeouts() -> None:
    java, timeouts = Java(), Timeouts()
    service = SettingsService(
        SettingsRepository(ApplicationSettings(java_executable="C:/jdk/java.exe", stop_timeout_seconds=120)),
        java,
        timeouts,
    )  # type: ignore[arg-type]

    service.apply()

    assert java.configured == ["C:/jdk/java.exe"]
    assert timeouts.calls == [(600, 120)]


def test_a_stored_java_that_no_longer_runs_falls_back_to_detection() -> None:
    java = Java()
    SettingsService(SettingsRepository(ApplicationSettings(java_executable="broken.exe")), java).apply()  # type: ignore[arg-type]

    assert java.configured == [None]


def test_update_validates_saves_and_applies() -> None:
    repository, java, timeouts = SettingsRepository(), Java(), Timeouts()
    service = SettingsService(repository, java, timeouts)  # type: ignore[arg-type]

    updated = service.update(stop_timeout_seconds=180, java_executable="C:/jdk/java.exe")

    assert repository.saved == [updated] and service.current == updated
    assert java.configured == ["C:/jdk/java.exe"]
    assert timeouts.calls == [(600, 180)]
    with pytest.raises(InvalidSettings):
        service.update(stop_timeout_seconds=1)
    with pytest.raises(InvalidJavaExecutable):
        service.update(java_executable="broken.exe")
    assert repository.saved == [updated]  # nothing invalid was saved


@pytest.mark.parametrize(
    "values",
    [{"language": "fr"}, {"stop_timeout_seconds": 5}, {"startup_timeout_seconds": 10_000}, {"java_executable": " "}],
)
def test_invalid_settings_are_rejected(values: dict[str, object]) -> None:
    with pytest.raises(InvalidSettings):
        ApplicationSettings(**values)  # type: ignore[arg-type]
