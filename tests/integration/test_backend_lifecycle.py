"""End-to-end backend lifecycle through the new architecture, with a controlled fake Java.

The fake "Java" is a small launcher (a ``.bat`` file on Windows, a shell script
elsewhere) that runs a Python script with the exact arguments the real launch
path builds: ``<java> -Xms..M -Xmx..M -jar <jar> nogui``. The script behaves
according to the content of the provisioned JAR file, which proves that the
JAR copied by provisioning is the one being launched. No Minecraft, Java or
network access is required.
"""

from __future__ import annotations

import os
import stat
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Event

import pytest

from mcserver.application.errors import ActiveServerAlreadyExists, ServerStartFailed
from mcserver.application.ports import OutputStream, ServerOutputLine
from mcserver.bootstrap.server_runtime import ServerRuntime, build_server_runtime
from mcserver.domain.lifecycle import ServerState
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.java_runtime import JavaRuntime, JavaRuntimeResolver, JavaRuntimeSource
from mcserver.infrastructure.server_configuration import ServerConfigurationError
from mcserver.infrastructure.server_configuration_store import StoredServerLaunchSettings

WAIT = 10.0

FAKE_SERVER = r"""
import os
import sys

args = sys.argv[1:]
jar = args[args.index("-jar") + 1]
with open(jar, encoding="utf-8") as file:
    behaviour = file.read().strip()
print("cwd=" + os.getcwd(), flush=True)
print("args=" + "|".join(args), flush=True)
print("jar-content=" + behaviour, flush=True)
print("loading libraries", file=sys.stderr, flush=True)
if behaviour == "crash-on-start":
    print("Failed to start the minecraft server", file=sys.stderr, flush=True)
    sys.exit(3)
print('Done (0.1s)! For help, type "help"', flush=True)
for line in sys.stdin:
    if line.strip() == "stop":
        print("Stopping the server", flush=True)
        sys.exit(0)
"""


class FakeJavaResolver(JavaRuntimeResolver):
    """Resolve "Java" to the controlled launcher without probing the system."""

    def __init__(self, launcher: Path) -> None:
        super().__init__()
        self._launcher = launcher

    def resolve(self) -> JavaRuntime:
        return JavaRuntime(self._launcher, JavaRuntimeSource.SYSTEM)


@pytest.fixture
def fake_java(tmp_path: Path) -> Path:
    tools = tmp_path / "tools"
    tools.mkdir()
    script = tools / "fake_server.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    if os.name == "nt":
        launcher = tools / "java.bat"
        launcher.write_text(f'@"{sys.executable}" -u "{script}" %*\r\n', encoding="utf-8")
    else:
        launcher = tools / "java"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" -u "{script}" "$@"\n', encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    return launcher


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "servers"


@pytest.fixture
def runtime(root: Path, fake_java: Path) -> Iterator[ServerRuntime]:
    with build_server_runtime(root, FakeJavaResolver(fake_java), launch_from_configuration_store=True) as built:
        yield built


def make_jar(tmp_path: Path, name: str, behaviour: str) -> Path:
    downloads = tmp_path / "downloads"
    downloads.mkdir(exist_ok=True)
    jar = downloads / name
    jar.write_text(behaviour, encoding="utf-8")
    return jar


def create(runtime: ServerRuntime, server_id: str, source: Path) -> ServerConfiguration:
    result = runtime.server_creation.create_server(
        server_id=server_id, directory=server_id, jar_file="server.jar", memory_mb=1024, source_jar=str(source)
    )
    return result.configuration


def wait_until(condition: Callable[[], bool], timeout: float = WAIT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


class Console:
    """A subscriber like a future GUI console: collects lines and signals markers."""

    def __init__(self) -> None:
        self.lines: list[ServerOutputLine] = []
        self.ready = Event()
        self.stopping = Event()

    def __call__(self, line: ServerOutputLine) -> None:
        self.lines.append(line)
        if line.text.startswith("Done ("):
            self.ready.set()
        if line.text == "Stopping the server":
            self.stopping.set()

    def texts(self, stream: OutputStream | None = None) -> list[str]:
        return [line.text for line in self.lines if stream is None or line.stream is stream]


def test_create_launch_observe_and_stop_through_the_new_configuration_store(
    runtime: ServerRuntime, root: Path, tmp_path: Path
) -> None:
    # Unrelated data that must survive the whole lifecycle.
    lobby = runtime.management.create_server(
        server_id="lobby", directory="lobby", jar_file="velocity.jar", memory_mb=512
    )
    (root / "notes.txt").write_text("keep me", encoding="utf-8")
    source = make_jar(tmp_path, "paper-1.21.jar", "normal")

    # Create + persist + provision.
    created = create(runtime, "survival", source)
    assert runtime.management.get_server("survival") == created
    assert runtime.configurations.get("survival") == created
    server_directory = (root / "survival").resolve()
    assert (server_directory / "server.jar").read_text(encoding="utf-8") == "normal"

    # Launch settings come from the new store (not servers_config.json, which does not exist).
    assert not (root / "servers_config.json").exists()
    settings = StoredServerLaunchSettings(runtime.configurations, root).get_launch_settings("survival")
    assert settings.working_directory == server_directory
    assert settings.server_jar_path == server_directory / "server.jar"

    console = Console()
    unsubscribe = runtime.output.subscribe(console)

    # Start.
    runtime.coordinator.start_server("survival")
    assert runtime.coordinator.active_server_id == "survival"
    assert runtime.coordinator.state is ServerState.RUNNING
    assert console.ready.wait(WAIT), console.texts()

    # Single active server policy.
    with pytest.raises(ActiveServerAlreadyExists):
        runtime.coordinator.start_server("lobby")

    # The process ran the provisioned JAR in its directory with the configured arguments.
    stdout = console.texts(OutputStream.STDOUT)
    assert f"cwd={server_directory}" in stdout
    assert "jar-content=normal" in stdout
    args_line = next(text for text in stdout if text.startswith("args="))
    assert args_line == f"args=-Xms1024M|-Xmx1024M|-jar|{server_directory / 'server.jar'}|nogui"
    # stdout and stderr are separate pipes read by separate threads: order is only kept per stream.
    assert wait_until(lambda: "loading libraries" in console.texts(OutputStream.STDERR))
    assert {line.server_id for line in console.lines} == {"survival"}

    # Graceful stop.
    assert runtime.coordinator.stop_server(timeout=WAIT) is True
    assert console.stopping.wait(WAIT)
    assert runtime.coordinator.active_server_id is None
    assert runtime.coordinator.state is ServerState.STOPPED
    assert runtime.coordinator.stop_server(timeout=WAIT) is False  # repeated stop is safe

    # A late subscriber (e.g. a reopened console view) receives the retained history.
    assert runtime.output.flush(WAIT)
    unsubscribe()
    late: list[str] = []
    stop_late = runtime.output.subscribe(lambda line: late.append(line.text))
    assert runtime.output.flush(WAIT)
    assert late == console.texts()
    stop_late()
    runtime.output.publish("survival", OutputStream.STDOUT, "after unsubscribe")
    assert runtime.output.flush(WAIT)
    assert "after unsubscribe" not in console.texts()

    # Nothing unrelated was touched; the slot is free for another server.
    assert runtime.management.get_server("lobby") == lobby
    assert (root / "notes.txt").read_text(encoding="utf-8") == "keep me"
    assert (server_directory / "server.jar").read_text(encoding="utf-8") == "normal"


def test_unexpected_exit_during_startup_releases_the_reservation(runtime: ServerRuntime, tmp_path: Path) -> None:
    create(runtime, "broken", make_jar(tmp_path, "broken.jar", "crash-on-start"))
    console = Console()
    runtime.output.subscribe(console)

    runtime.coordinator.start_server("broken")

    assert wait_until(lambda: runtime.coordinator.active_server_id is None)
    assert runtime.coordinator.state is ServerState.STOPPED
    assert runtime.output.flush(WAIT)
    assert "Failed to start the minecraft server" in console.texts(OutputStream.STDERR)
    assert runtime.coordinator.stop_server(timeout=WAIT) is False

    # The coordinator is usable again.
    create(runtime, "survival", make_jar(tmp_path, "paper.jar", "normal"))
    runtime.coordinator.start_server("survival")
    assert runtime.coordinator.state is ServerState.RUNNING
    assert runtime.coordinator.stop_server(timeout=WAIT) is True
    assert runtime.coordinator.state is ServerState.STOPPED


def test_failed_launches_leave_the_coordinator_stopped_and_reusable(
    root: Path, tmp_path: Path, fake_java: Path
) -> None:
    missing_java = FakeJavaResolver(tmp_path / "no-such-java.exe")
    with build_server_runtime(root, missing_java, launch_from_configuration_store=True) as runtime:
        create(runtime, "survival", make_jar(tmp_path, "paper.jar", "normal"))

        with pytest.raises(ServerStartFailed):
            runtime.coordinator.start_server("survival")  # Java executable cannot be started
        assert runtime.coordinator.active_server_id is None
        assert runtime.coordinator.state is ServerState.STOPPED

        with pytest.raises(ServerStartFailed):
            runtime.coordinator.start_server("unknown")  # no such configuration
        assert runtime.coordinator.active_server_id is None
        assert runtime.coordinator.state is ServerState.STOPPED

    with build_server_runtime(root, FakeJavaResolver(fake_java), launch_from_configuration_store=True) as runtime:
        runtime.coordinator.start_server("survival")
        assert runtime.coordinator.state is ServerState.RUNNING
        assert runtime.coordinator.stop_server(timeout=WAIT) is True


def test_default_runtime_still_launches_from_legacy_file_only(root: Path, tmp_path: Path, fake_java: Path) -> None:
    """Documents the transition state: servers created in the new store need the opt-in flag."""
    with build_server_runtime(root, FakeJavaResolver(fake_java)) as runtime:
        create(runtime, "survival", make_jar(tmp_path, "paper.jar", "normal"))

        with pytest.raises(ServerStartFailed) as error:
            runtime.coordinator.start_server("survival")

        assert isinstance(error.value.__cause__, ServerConfigurationError)
        assert runtime.coordinator.state is ServerState.STOPPED
        assert runtime.management.get_server("survival").jar_file == "server.jar"
