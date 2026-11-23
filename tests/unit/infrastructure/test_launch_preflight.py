"""Launch checks of the runner factory: EULA, Java requirement, world lock (M1-BE-01/05/06)."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

from mcserver.application.errors import (
    EulaNotAccepted,
    JavaNotFound,
    JavaVersionTooOld,
    ServerPortInUse,
    ServerWorldInUse,
)
from mcserver.application.ports import JavaInstallation, StartOptions
from mcserver.infrastructure.jar_version import read_jar_version
from mcserver.infrastructure.process_runner import SubprocessServerRunner
from mcserver.infrastructure.server_configuration import (
    ConfiguredServerRunnerFactory,
    ServerLaunchSettings,
    locked_world,
)
from mcserver.infrastructure.server_files import write_eula_file


class FakeJava:
    def __init__(self, major: int | None) -> None:
        self.major = major
        self.requests: list[int | None] = []
        self.configured_executable: str | None = None

    def find(self, minimum_major: int | None = None) -> JavaInstallation:
        self.requests.append(minimum_major)
        if self.major is None:
            raise JavaNotFound(minimum_major)
        return JavaInstallation(f"C:/java{self.major}/bin/java.exe", self.major, "installed")

    def configure(self, executable: str | None) -> JavaInstallation | None:
        return None


class Settings:
    def __init__(self, directory: Path, jar: Path) -> None:
        self.directory = directory
        self.jar = jar

    def get_launch_settings(self, server_id: str) -> ServerLaunchSettings:
        return ServerLaunchSettings(server_id, self.jar, self.directory, 2048)


def server(tmp_path: Path, jar_name: str = "server.jar", version_json: dict[str, object] | None = None) -> Settings:
    directory = tmp_path / "survival"
    directory.mkdir()
    jar = directory / jar_name
    with zipfile.ZipFile(jar, "w") as archive:
        if version_json is not None:
            archive.writestr("version.json", json.dumps(version_json))
    return Settings(directory, jar)


def test_start_without_eula_is_refused(tmp_path: Path) -> None:
    settings = server(tmp_path)

    with pytest.raises(EulaNotAccepted):
        ConfiguredServerRunnerFactory(settings, FakeJava(21)).create("survival")


def test_ready_server_gets_a_runner_with_memory_nogui_and_the_found_java(tmp_path: Path) -> None:
    settings = server(tmp_path, version_json={"id": "1.21.4", "java_version": 21})
    write_eula_file(settings.directory, "survival")
    java = FakeJava(21)

    prepared = ConfiguredServerRunnerFactory(settings, java).create("survival", StartOptions())

    assert isinstance(prepared.runner, SubprocessServerRunner)
    assert prepared.runner.command == (
        "C:/java21/bin/java.exe",
        "-Xms2048M",
        "-Xmx2048M",
        "-jar",
        str(settings.jar),
        "nogui",
    )
    assert prepared.warnings == ()
    assert java.requests == [21]


def test_too_old_java_blocks_unless_the_user_overrides(tmp_path: Path) -> None:
    settings = server(tmp_path, version_json={"id": "26.1", "java_version": 25})
    write_eula_file(settings.directory, "survival")
    factory = ConfiguredServerRunnerFactory(settings, FakeJava(21))

    with pytest.raises(JavaVersionTooOld) as error:
        factory.create("survival")
    assert (error.value.required_major, error.value.found_major) == (25, 21)

    prepared = factory.create("survival", StartOptions(allow_outdated_java=True))
    assert [warning.code for warning in prepared.warnings] == ["java_outdated_allowed"]


def test_requirement_comes_from_the_verified_table_when_the_jar_declares_none(tmp_path: Path) -> None:
    settings = server(tmp_path, jar_name="paper-1.20.4-499.jar")
    write_eula_file(settings.directory, "survival")
    java = FakeJava(17)

    prepared = ConfiguredServerRunnerFactory(settings, java).create("survival")

    assert java.requests == [17]
    assert prepared.warnings == ()


def test_unverified_version_only_warns_and_assumes_nothing(tmp_path: Path) -> None:
    settings = server(tmp_path, jar_name="paper-27.1-1.jar")
    write_eula_file(settings.directory, "survival")
    java = FakeJava(8)

    prepared = ConfiguredServerRunnerFactory(settings, java).create("survival")

    assert java.requests == [None]
    assert [warning.code for warning in prepared.warnings] == ["java_requirement_unknown"]
    assert prepared.warnings[0].params == {"version": "27.1", "java_major": 8}


def test_missing_java_is_reported(tmp_path: Path) -> None:
    settings = server(tmp_path, version_json={"id": "1.21.4"})
    write_eula_file(settings.directory, "survival")

    with pytest.raises(JavaNotFound) as error:
        ConfiguredServerRunnerFactory(settings, FakeJava(None)).create("survival")
    assert error.value.required_major == 21


def test_reads_jar_version_from_version_json_or_file_name(tmp_path: Path) -> None:
    jar = tmp_path / "server.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("version.json", json.dumps({"id": "1.21.11", "java_version": 21}))
    named = tmp_path / "paper-1.21.1-123.jar"
    named.write_bytes(b"not a zip")

    assert read_jar_version(jar).version == (1, 21, 11)
    assert read_jar_version(jar).declared_java_major == 21
    assert read_jar_version(named).version == (1, 21, 1)
    assert read_jar_version(tmp_path / "custom.jar").version is None


def test_unlocked_or_missing_world_is_not_in_use(tmp_path: Path) -> None:
    assert locked_world(tmp_path) is None
    (tmp_path / "world").mkdir()
    (tmp_path / "world" / "session.lock").write_bytes(b"x")

    assert locked_world(tmp_path) is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows byte-range lock semantics")
def test_world_locked_by_another_handle_is_in_use(tmp_path: Path) -> None:
    import msvcrt

    (tmp_path / "server.properties").write_text("level-name=survival_world\n", encoding="utf-8")
    world = tmp_path / "survival_world"
    world.mkdir()
    lock = world / "session.lock"
    lock.write_bytes(b"x")
    with lock.open("r+b") as holder:
        msvcrt.locking(holder.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            assert locked_world(tmp_path) == "survival_world"
            settings = Settings(tmp_path, tmp_path / "server.jar")
            write_eula_file(tmp_path, "survival")
            with pytest.raises(ServerWorldInUse):
                ConfiguredServerRunnerFactory(settings, FakeJava(21)).create("survival")
        finally:
            msvcrt.locking(holder.fileno(), msvcrt.LK_UNLCK, 1)


def test_busy_server_port_is_refused_before_launching(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = server(tmp_path, version_json={"id": "1.21.4", "java_version": 21})
    write_eula_file(settings.directory, "survival")
    (settings.directory / "server.properties").write_text("server-port=25600\n", encoding="utf-8")
    probed: list[tuple[str, int]] = []

    def busy(host: str, port: int) -> bool:
        probed.append((host, port))
        return True

    monkeypatch.setattr("mcserver.infrastructure.server_configuration.port_in_use", busy)

    with pytest.raises(ServerPortInUse) as error:
        ConfiguredServerRunnerFactory(settings, FakeJava(21)).create("survival")

    assert error.value.port == 25600 and probed == [("", 25600)]
