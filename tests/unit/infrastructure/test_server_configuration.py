"""Tests for loading legacy server settings into v2 process configuration."""

import json
from pathlib import Path

import pytest

from mcserver.application.server_output import ServerOutputBuffer
from mcserver.infrastructure.process_runner import SubprocessServerRunner
from mcserver.infrastructure.server_configuration import (
    ConfiguredServerRunnerFactory,
    LegacyServerConfigurationRepository,
    ServerConfigurationError,
)


def write_config(servers_directory: Path, entry: dict[str, object]) -> None:
    """Write one legacy-compatible server configuration entry."""
    (servers_directory / "servers_config.json").write_text(json.dumps({"survival": entry}), encoding="utf-8")


def test_reads_legacy_server_launch_settings(tmp_path: Path) -> None:
    servers_directory = tmp_path / "servers"
    server_directory = servers_directory / "survival"
    server_directory.mkdir(parents=True)
    jar = server_directory / "paper.jar"
    jar.write_bytes(b"jar")
    write_config(
        servers_directory,
        {"directory": str(server_directory), "jar_path": str(jar), "core_name": "paper.jar", "ram": 4096},
    )

    settings = LegacyServerConfigurationRepository(servers_directory).get_launch_settings("survival")

    assert settings.server_jar_path == jar.resolve()
    assert settings.working_directory == server_directory.resolve()
    assert settings.memory_megabytes == 4096


def test_rejects_server_directory_outside_managed_root(tmp_path: Path) -> None:
    servers_directory = tmp_path / "servers"
    servers_directory.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    write_config(servers_directory, {"directory": str(outside), "core_name": "paper.jar", "ram": 1024})

    with pytest.raises(ServerConfigurationError, match="outside"):
        LegacyServerConfigurationRepository(servers_directory).get_launch_settings("survival")


def test_factory_builds_runner_with_server_memory_and_nogui(tmp_path: Path) -> None:
    servers_directory = tmp_path / "servers"
    server_directory = servers_directory / "survival"
    server_directory.mkdir(parents=True)
    jar = server_directory / "paper.jar"
    jar.write_bytes(b"jar")
    write_config(servers_directory, {"directory": str(server_directory), "core_name": "paper.jar", "ram": 2048})

    runner = ConfiguredServerRunnerFactory(LegacyServerConfigurationRepository(servers_directory), "java").create(
        "survival"
    )

    assert isinstance(runner, SubprocessServerRunner)
    assert runner.command == ("java", "-Xms2048M", "-Xmx2048M", "-jar", str(jar.resolve()), "nogui")


def test_factory_passes_output_sink_to_runner(tmp_path: Path) -> None:
    servers_directory = tmp_path / "servers"
    server_directory = servers_directory / "survival"
    server_directory.mkdir(parents=True)
    (server_directory / "paper.jar").write_bytes(b"jar")
    write_config(servers_directory, {"directory": str(server_directory), "core_name": "paper.jar", "ram": 1024})
    sink = ServerOutputBuffer()

    runner = ConfiguredServerRunnerFactory(
        LegacyServerConfigurationRepository(servers_directory), "java", output_sink=sink
    ).create("survival")

    assert isinstance(runner, SubprocessServerRunner)
    assert runner._output_sink is sink
