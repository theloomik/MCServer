"""Tests for composing the server runtime without launching Java."""

import json
from pathlib import Path

import pytest

from mcserver.application.auto_restart import AutoRestartPolicy
from mcserver.application.backup_schedule import ScheduledBackups
from mcserver.application.backups import BackupService
from mcserver.application.errors import (
    EulaNotAccepted,
    InvalidSourceJar,
    JavaNotFound,
    ServerDirectoryAlreadyExists,
    ServerStartFailed,
    ServerStopFailed,
)
from mcserver.application.java_setup import JavaSetup
from mcserver.application.ports import JavaInstallation, OutputStream
from mcserver.application.server_activity import ServerActivity
from mcserver.application.server_address import ServerAddressLookup
from mcserver.application.server_adoption import ServerAdoption
from mcserver.application.server_catalog import ServerJarCatalog
from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_creation import ServerCreation
from mcserver.application.server_health import ServerHealth
from mcserver.application.server_management import ServerManagement
from mcserver.application.server_metrics import ServerMetrics
from mcserver.application.server_output import ServerOutputBuffer
from mcserver.application.server_properties import ServerPropertiesService
from mcserver.application.server_provisioning import ProvisionedServer, ServerProvisioning
from mcserver.application.settings import SettingsService
from mcserver.application.worlds import WorldService
from mcserver.bootstrap.server_runtime import (
    ServerRuntime,
    build_server_coordinator,
    build_server_creation,
    build_server_management,
    build_server_provisioning,
    build_server_runtime,
)
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.process_runner import SubprocessServerRunner
from mcserver.infrastructure.psutil_metrics import PsutilProcessMetrics
from mcserver.infrastructure.server_configuration_store import (
    JsonServerConfigurationRepository,
    StoredServerLaunchSettings,
)
from mcserver.infrastructure.server_folders import LocalServerFolderAdoption
from mcserver.infrastructure.server_properties_file import FileServerPropertiesStore
from mcserver.infrastructure.settings_store import JsonApplicationSettingsStore
from mcserver.infrastructure.world_folders import LocalWorldStore
from mcserver.infrastructure.zip_backup_store import ZipBackupStore
from tests.runtime_fakes import FakeRunner, FakeRunnerFactory, ManualScheduler, MemoryMarkers

WAIT = 3.0


class StubJavaResolver:
    """Return a fixed Java without probing the system."""

    configured_executable = None

    def find(self, minimum_major: int | None = None) -> JavaInstallation:
        return JavaInstallation("java", 21, "path")

    def configure(self, executable: str | None) -> JavaInstallation | None:
        return None


class MissingJavaResolver(StubJavaResolver):
    def find(self, minimum_major: int | None = None) -> JavaInstallation:
        raise JavaNotFound(minimum_major)


def runtime_with(runner: FakeRunner) -> ServerRuntime:
    # Never read or written by these lifecycle tests.
    unused_root = Path("unused-servers-root")
    configurations = JsonServerConfigurationRepository(unused_root)
    coordinator = ServerCoordinator(FakeRunnerFactory(runner), scheduler=ManualScheduler())
    return ServerRuntime(
        coordinator=coordinator,
        output=ServerOutputBuffer(),
        configurations=configurations,
        management=build_server_management(unused_root, configurations),
        provisioning=build_server_provisioning(unused_root, configurations),
        server_creation=build_server_creation(unused_root, configurations),
        java=JavaSetup(StubJavaResolver()),
        health=ServerHealth(MemoryMarkers()),
        settings=SettingsService(JsonApplicationSettingsStore(unused_root), StubJavaResolver()),
        adoption=ServerAdoption(
            build_server_management(unused_root, configurations), LocalServerFolderAdoption(unused_root)
        ),
        properties=ServerPropertiesService(FileServerPropertiesStore(unused_root, configurations)),
        metrics=ServerMetrics(coordinator, PsutilProcessMetrics(), configurations, lambda: 0.0),
        backups=BackupService(configurations, coordinator, ZipBackupStore(unused_root)),
        scheduled_backups=ScheduledBackups(
            ZipBackupStore(unused_root),
            BackupService(configurations, coordinator, ZipBackupStore(unused_root)),
            coordinator,
        ),
        activity=ServerActivity(),
        jar_catalog=ServerJarCatalog({}, None),  # type: ignore[arg-type]
        worlds=WorldService(
            configurations,
            LocalWorldStore(unused_root),
            ServerPropertiesService(FileServerPropertiesStore(unused_root, configurations)),
            lambda: None,
        ),
        auto_restart=AutoRestartPolicy(lambda: False),
        address=ServerAddressLookup(
            ServerPropertiesService(FileServerPropertiesStore(unused_root, configurations)), lambda: None
        ),
    )


def write_legacy_server(root: Path, name: str, ram: object = 1024) -> Path:
    """Create a server folder with a JAR and a legacy servers_config.json entry for it."""
    server_directory = root / name
    server_directory.mkdir(parents=True, exist_ok=True)
    (server_directory / "paper.jar").write_bytes(b"jar")
    legacy_path = root / "servers_config.json"
    entries = json.loads(legacy_path.read_text(encoding="utf-8")) if legacy_path.exists() else {}
    entries[name] = {"core_name": "paper.jar", "ram": ram, "directory": str(server_directory)}
    legacy_path.write_text(json.dumps(entries), encoding="utf-8")
    return server_directory


def make_source_jar(tmp_path: Path) -> Path:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    jar = downloads / "paper-1.21.jar"
    jar.write_bytes(b"jar bytes")
    return jar


def test_runtime_provisioning_shares_repository_and_uses_servers_root(tmp_path: Path) -> None:
    root = tmp_path / "servers"
    source = make_source_jar(tmp_path)

    with build_server_runtime(root, StubJavaResolver()) as runtime:
        assert isinstance(runtime.provisioning, ServerProvisioning)
        assert runtime.provisioning._repository is runtime.configurations  # type: ignore[attr-defined]
        runtime.management.create_server(
            server_id="creative", directory="creative-files", jar_file="paper.jar", memory_mb=4096
        )

        result = runtime.provisioning.provision_server("creative", str(source))

        assert result == ProvisionedServer(runtime.management.get_server("creative"), str(source))
        assert (root / "creative-files" / "paper.jar").read_bytes() == b"jar bytes"
        assert runtime.management.list_servers() == (result.configuration,)


def test_provisioning_works_without_java(tmp_path: Path) -> None:
    source = make_source_jar(tmp_path)
    build_server_management(tmp_path).create_server(
        server_id="survival", directory="survival", jar_file="server.jar", memory_mb=2048
    )

    build_server_provisioning(tmp_path).provision_server("survival", str(source))

    assert (tmp_path / "survival" / "server.jar").read_bytes() == b"jar bytes"


def test_provisioned_server_is_launchable_from_configuration_store(tmp_path: Path) -> None:
    root = tmp_path / "servers"
    source = make_source_jar(tmp_path)

    with build_server_runtime(root, StubJavaResolver()) as runtime:
        runtime.management.create_server(
            server_id="survival", directory="survival", jar_file="paper.jar", memory_mb=2048
        )
        runtime.provisioning.provision_server("survival", str(source), accept_eula=True)

        runner = runtime.coordinator._runner_factory.create("survival").runner  # type: ignore[attr-defined]

        assert isinstance(runner, SubprocessServerRunner)
        assert Path(runner.command[-2]).read_bytes() == b"jar bytes"


def test_provisioning_existing_directory_keeps_user_files(tmp_path: Path) -> None:
    source = make_source_jar(tmp_path)
    (tmp_path / "survival").mkdir()
    (tmp_path / "survival" / "level.dat").write_bytes(b"world")
    build_server_management(tmp_path).create_server(
        server_id="survival", directory="survival", jar_file="paper.jar", memory_mb=2048
    )

    with pytest.raises(ServerDirectoryAlreadyExists):
        build_server_provisioning(tmp_path).provision_server("survival", str(source))
    assert sorted(path.name for path in (tmp_path / "survival").iterdir()) == ["level.dat"]


def test_runtime_server_creation_reuses_runtime_management_and_provisioning(tmp_path: Path) -> None:
    root = tmp_path / "servers"
    source = make_source_jar(tmp_path)

    with build_server_runtime(root, StubJavaResolver()) as runtime:
        creation = runtime.server_creation
        assert isinstance(creation, ServerCreation)
        assert creation._management is runtime.management  # type: ignore[attr-defined]
        assert creation._provisioning is runtime.provisioning  # type: ignore[attr-defined]

        result = creation.create_server(
            server_id="survival",
            directory="survival",
            jar_file="paper.jar",
            memory_mb=2048,
            source_jar=str(source),
            accept_eula=True,
        )

        assert runtime.configurations.get("survival") == result.configuration
        assert (root / "survival" / "paper.jar").read_bytes() == b"jar bytes"
        assert "eula=true" in (root / "survival" / "eula.txt").read_text(encoding="utf-8")
        runner = runtime.coordinator._runner_factory.create("survival").runner  # type: ignore[attr-defined]
        assert Path(runner.command[-2]) == (root / "survival" / "paper.jar").resolve()


def test_server_creation_builds_and_works_without_java(tmp_path: Path) -> None:
    source = make_source_jar(tmp_path)
    creation = build_server_creation(tmp_path)

    creation.create_server(
        server_id="survival", directory="survival", jar_file="server.jar", memory_mb=2048, source_jar=str(source)
    )

    assert build_server_management(tmp_path).get_server("survival").jar_file == "server.jar"
    assert (tmp_path / "survival" / "server.jar").read_bytes() == b"jar bytes"


def test_server_creation_failure_on_real_files_leaves_no_record_and_keeps_user_data(tmp_path: Path) -> None:
    source = make_source_jar(tmp_path)
    management = build_server_management(tmp_path)
    management.create_server(server_id="lobby", directory="lobby", jar_file="velocity.jar", memory_mb=1024)
    (tmp_path / "survival").mkdir()
    (tmp_path / "survival" / "level.dat").write_bytes(b"world")
    creation = build_server_creation(tmp_path)

    with pytest.raises(ServerDirectoryAlreadyExists):
        creation.create_server(
            server_id="survival", directory="survival", jar_file="paper.jar", memory_mb=2048, source_jar=str(source)
        )
    with pytest.raises(InvalidSourceJar):
        creation.create_server(
            server_id="creative",
            directory="creative",
            jar_file="paper.jar",
            memory_mb=2048,
            source_jar=str(tmp_path / "missing.jar"),
        )

    assert [server.server_id for server in management.list_servers()] == ["lobby"]
    assert sorted(path.name for path in (tmp_path / "survival").iterdir()) == ["level.dat"]
    assert not (tmp_path / "creative").exists()
    assert source.read_bytes() == b"jar bytes"


def test_runtime_shares_one_output_buffer_with_runner_factory(tmp_path: Path) -> None:
    with build_server_runtime(tmp_path, StubJavaResolver(), output_capacity=50) as runtime:
        assert isinstance(runtime.coordinator, ServerCoordinator)
        assert isinstance(runtime.output, ServerOutputBuffer)
        assert runtime.output.capacity == 50
        assert runtime.coordinator._runner_factory._output_sink is runtime.output  # type: ignore[attr-defined]


def test_build_server_coordinator_remains_available(tmp_path: Path) -> None:
    assert isinstance(build_server_coordinator(tmp_path, StubJavaResolver()), ServerCoordinator)


def test_runtime_launches_only_from_the_configuration_store(tmp_path: Path) -> None:
    write_legacy_server(tmp_path, "legacy-only")
    with build_server_runtime(tmp_path, StubJavaResolver()) as runtime:
        factory = runtime.coordinator._runner_factory  # type: ignore[attr-defined]

        assert isinstance(runtime.configurations, JsonServerConfigurationRepository)
        assert runtime.configurations.path.parent == tmp_path.resolve()
        assert isinstance(factory._repository, StoredServerLaunchSettings)
        with pytest.raises(ServerStartFailed):
            runtime.coordinator.start_server("legacy-only")  # 0.9.1 servers must be imported first (ADR 0009)
    assert not runtime.configurations.path.exists()


def test_runtime_can_launch_from_configuration_store(tmp_path: Path) -> None:
    with build_server_runtime(tmp_path, StubJavaResolver()) as runtime:
        runtime.configurations.add(ServerConfiguration("survival", "survival", "paper.jar", 2048))
        factory = runtime.coordinator._runner_factory  # type: ignore[attr-defined]
        (tmp_path / "survival").mkdir()
        with pytest.raises(EulaNotAccepted):
            factory.create("survival")
        (tmp_path / "survival" / "eula.txt").write_text("eula=true\n", encoding="utf-8")

        runner = factory.create("survival").runner

        assert isinstance(factory._repository, StoredServerLaunchSettings)
        assert isinstance(runner, SubprocessServerRunner)
        jar = tmp_path.resolve() / "survival" / "paper.jar"
        assert runner.command == ("java", "-Xms2048M", "-Xmx2048M", "-jar", str(jar), "nogui")


def test_runtime_builds_without_java_and_reports_it(tmp_path: Path) -> None:
    with build_server_runtime(tmp_path, MissingJavaResolver()) as runtime:
        assert not runtime.java.status().available
        assert runtime.health.unclean_shutdowns() == ()


def test_runtime_management_shares_the_runtime_repository(tmp_path: Path) -> None:
    with build_server_runtime(tmp_path, StubJavaResolver()) as runtime:
        assert isinstance(runtime.management, ServerManagement)
        assert runtime.management._repository is runtime.configurations  # type: ignore[attr-defined]

        created = runtime.management.create_server(
            server_id="creative", directory="creative", jar_file="paper.jar", memory_mb=4096
        )

        assert runtime.configurations.get("creative") == created


def test_server_management_can_be_built_without_java(tmp_path: Path) -> None:

    management = build_server_management(tmp_path)

    assert management.list_servers() == ()


def test_management_full_cycle_against_real_files_keeps_server_files(tmp_path: Path) -> None:
    management = build_server_management(tmp_path)
    server_directory = tmp_path / "creative"
    server_directory.mkdir()
    (server_directory / "paper.jar").write_bytes(b"jar")
    (server_directory / "world").mkdir()
    (server_directory / "world" / "level.dat").write_bytes(b"world")

    management.create_server(server_id="creative", directory="creative", jar_file="paper.jar", memory_mb=4096)
    updated = management.update_server("creative", jar_file="purpur.jar", memory_mb=6144)
    assert build_server_management(tmp_path).get_server("creative") == updated

    management.delete_server("creative")

    assert management.list_servers() == ()
    assert (server_directory / "paper.jar").read_bytes() == b"jar"
    assert (server_directory / "world" / "level.dat").read_bytes() == b"world"


def test_legacy_import_through_bootstrap_is_explicit_repeatable_and_read_only(tmp_path: Path) -> None:
    write_legacy_server(tmp_path, "survival")
    write_legacy_server(tmp_path, "broken", ram="lots")
    legacy_before = (tmp_path / "servers_config.json").read_bytes()

    with build_server_runtime(tmp_path, StubJavaResolver()) as runtime:
        assert runtime.management.list_servers() == ()  # nothing imported on startup

        first = runtime.management.import_legacy_servers()
        second = runtime.management.import_legacy_servers()

        assert (first.imported, first.skipped) == (("survival",), ())
        assert [rejected.server_id for rejected in first.rejected] == ["broken"]
        assert (second.imported_count, second.skipped_count, second.rejected_count) == (0, 1, 1)
        assert runtime.configurations.get("survival") == ServerConfiguration("survival", "survival", "paper.jar", 1024)
    assert (tmp_path / "servers_config.json").read_bytes() == legacy_before


def test_close_stops_active_server_and_ends_dispatcher_thread() -> None:
    runner = FakeRunner()
    runtime = runtime_with(runner)
    runtime.output.subscribe(lambda _line: None)
    dispatcher = runtime.output._dispatcher
    runtime.coordinator.start_server("survival")

    assert runtime.close(timeout=WAIT) is True

    assert runner.stopped == [WAIT]
    assert runtime.coordinator.active_server_id is None
    assert dispatcher is not None and not dispatcher.is_alive()


def test_close_without_active_server_or_subscribers_is_safe() -> None:
    runtime = runtime_with(FakeRunner())

    assert runtime.close(timeout=WAIT) is True
    assert runtime.close(timeout=WAIT) is True


def test_close_returns_false_when_the_stop_times_out_and_never_kills() -> None:
    runner = FakeRunner(stop_exits=False)
    runtime = runtime_with(runner)
    runtime.coordinator.start_server("survival")

    assert runtime.close(timeout=0.0) is False

    assert runner.killed == 0
    assert runtime.coordinator.active_server_id == "survival"


def test_close_ends_dispatcher_even_when_server_stop_fails() -> None:
    failing = FakeRunner()
    failing.stop_error = RuntimeError("stop failed")
    runtime = runtime_with(failing)
    runtime.output.subscribe(lambda _line: None)
    dispatcher = runtime.output._dispatcher
    runtime.coordinator.start_server("survival")

    with pytest.raises(ServerStopFailed):
        runtime.close(timeout=WAIT)

    assert dispatcher is not None and not dispatcher.is_alive()
    with pytest.raises(RuntimeError, match="closed"):
        runtime.output.subscribe(lambda _line: None)


def test_context_manager_closes_runtime() -> None:
    received: list[str] = []
    with runtime_with(FakeRunner()) as runtime:
        runtime.output.subscribe(lambda line: received.append(line.text))
        runtime.output.publish("survival", OutputStream.STDOUT, "hello")
        assert runtime.output.flush(WAIT)
        dispatcher = runtime.output._dispatcher

    assert received == ["hello"]
    assert dispatcher is not None and not dispatcher.is_alive()
