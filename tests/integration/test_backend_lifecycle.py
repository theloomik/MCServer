"""End-to-end backend lifecycle with a controlled fake Minecraft server (M1-QA-03).

Create → accept EULA → start → readiness → console command → graceful stop,
plus the failure paths: startup timeout, slow save, ignored stop and explicit
kill, crash, missing EULA. See ``conftest.py`` for the fake server. No
Minecraft, Java or network access is required.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Event

import pytest

from mcserver.application.errors import (
    ActiveServerAlreadyExists,
    EulaNotAccepted,
    ServerStartFailed,
    ServerStopTimedOut,
)
from mcserver.application.ports import OutputStream, ServerOutputLine
from mcserver.application.server_coordinator import FailureKind
from mcserver.bootstrap.server_runtime import ServerRuntime, build_server_runtime
from mcserver.domain.diagnostics import FailureHint
from mcserver.domain.lifecycle import ServerState
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.server_configuration import ServerConfigurationError
from mcserver.infrastructure.server_configuration_store import StoredServerLaunchSettings
from mcserver.infrastructure.session_markers import MARKER_DIRECTORY, MARKER_FILE
from tests.integration.conftest import FakeJavaResolver

WAIT = 10.0


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "servers"


@pytest.fixture
def runtime(root: Path, fake_java: Path) -> Iterator[ServerRuntime]:
    with build_server_runtime(
        root, FakeJavaResolver(fake_java), launch_from_configuration_store=True, startup_timeout=3, stop_timeout=WAIT
    ) as built:
        yield built


def make_jar(tmp_path: Path, name: str, behaviour: str) -> Path:
    downloads = tmp_path / "downloads"
    downloads.mkdir(exist_ok=True)
    jar = downloads / name
    jar.write_text(behaviour, encoding="utf-8")
    return jar


def create(runtime: ServerRuntime, server_id: str, source: Path, *, accept_eula: bool = True) -> ServerConfiguration:
    result = runtime.server_creation.create_server(
        server_id=server_id,
        directory=server_id,
        jar_file="server.jar",
        memory_mb=1024,
        source_jar=str(source),
        accept_eula=accept_eula,
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
    """A subscriber like the GUI console: collects lines and signals markers."""

    def __init__(self) -> None:
        self.lines: list[ServerOutputLine] = []
        self.ready = Event()
        self.stopping = Event()

    def __call__(self, line: ServerOutputLine) -> None:
        self.lines.append(line)
        if "Done (" in line.text:
            self.ready.set()
        if line.text == "Stopping the server":
            self.stopping.set()

    def texts(self, stream: OutputStream | None = None) -> list[str]:
        return [line.text for line in self.lines if stream is None or line.stream is stream]


def marker(root: Path, server_id: str) -> Path:
    return root / server_id / MARKER_DIRECTORY / MARKER_FILE


def test_create_start_ready_command_and_graceful_stop(runtime: ServerRuntime, root: Path, tmp_path: Path) -> None:
    # Unrelated data that must survive the whole lifecycle.
    lobby = runtime.management.create_server(
        server_id="lobby", directory="lobby", jar_file="velocity.jar", memory_mb=512
    )
    (root / "notes.txt").write_text("keep me", encoding="utf-8")
    source = make_jar(tmp_path, "paper-1.21.jar", "require_eula=1 ready_delay=0.5")

    # Create + persist + provision + explicit EULA consent.
    created = create(runtime, "survival", source)
    assert runtime.configurations.get("survival") == created
    server_directory = (root / "survival").resolve()
    assert "eula=true" in (server_directory / "eula.txt").read_text(encoding="utf-8")
    settings = StoredServerLaunchSettings(runtime.configurations, root).get_launch_settings("survival")
    assert settings.server_jar_path == server_directory / "server.jar"

    console = Console()
    unsubscribe = runtime.output.subscribe(console)

    # Start: STARTING until the ready line, then RUNNING.
    report = runtime.coordinator.start_server("survival")
    assert [warning.code for warning in report.warnings] == ["java_requirement_unknown"]
    assert runtime.coordinator.state is ServerState.STARTING
    assert marker(root, "survival").is_file()
    assert console.ready.wait(WAIT), console.texts()
    assert wait_until(lambda: runtime.coordinator.state is ServerState.RUNNING)

    with pytest.raises(ActiveServerAlreadyExists):
        runtime.coordinator.start_server("lobby")

    stdout = console.texts(OutputStream.STDOUT)
    assert f"cwd={server_directory}" in stdout
    args_line = next(text for text in stdout if text.startswith("args="))
    assert args_line == f"args=-Xms1024M|-Xmx1024M|-jar|{server_directory / 'server.jar'}|nogui"

    # Console command: delivered to stdin and echoed into the shared output.
    runtime.coordinator.send_command("survival", "say hi")
    assert wait_until(lambda: "echo: say hi" in console.texts(OutputStream.STDOUT))
    assert "say hi" in console.texts(OutputStream.COMMAND)

    # Graceful stop clears the marker.
    assert runtime.coordinator.stop_server() is True
    assert console.stopping.wait(WAIT)
    assert runtime.coordinator.state is ServerState.STOPPED
    assert not marker(root, "survival").exists()
    assert runtime.coordinator.status().last_failure is None
    assert runtime.coordinator.stop_server() is False

    # A late subscriber receives the retained history.
    assert runtime.output.flush(WAIT)
    unsubscribe()
    late: list[str] = []
    runtime.output.subscribe(lambda line: late.append(line.text))
    assert runtime.output.flush(WAIT)
    assert late == console.texts()

    assert runtime.management.get_server("lobby") == lobby
    assert (root / "notes.txt").read_text(encoding="utf-8") == "keep me"
    assert (server_directory / "server.jar").read_text(encoding="utf-8") == "require_eula=1 ready_delay=0.5"


def test_server_without_eula_consent_is_not_started(runtime: ServerRuntime, root: Path, tmp_path: Path) -> None:
    create(runtime, "survival", make_jar(tmp_path, "paper.jar", "require_eula=1"), accept_eula=False)

    with pytest.raises(EulaNotAccepted):
        runtime.coordinator.start_server("survival")
    assert not (root / "survival" / "started.flag").exists()  # nothing was launched

    runtime.provisioning.accept_eula("survival")
    runtime.coordinator.start_server("survival")
    assert wait_until(lambda: runtime.coordinator.state is ServerState.RUNNING)
    assert runtime.coordinator.stop_server() is True


def test_startup_timeout_is_reported_and_stopped_gracefully(runtime: ServerRuntime, tmp_path: Path) -> None:
    create(runtime, "slow", make_jar(tmp_path, "slow.jar", "never_ready=1"))
    console = Console()
    runtime.output.subscribe(console)

    runtime.coordinator.start_server("slow")

    assert wait_until(lambda: runtime.coordinator.active_server_id is None, timeout=WAIT)
    failure = runtime.coordinator.status().last_failure
    assert failure is not None and failure.kind is FailureKind.START_TIMEOUT
    assert runtime.output.flush(WAIT)
    assert "Stopping the server" in console.texts()  # graceful: it received "stop"
    assert "Saved the world" in console.texts()


def test_slow_save_finishes_within_the_stop_timeout(runtime: ServerRuntime, root: Path, tmp_path: Path) -> None:
    create(runtime, "survival", make_jar(tmp_path, "paper.jar", "stop_delay=1.5"))
    console = Console()
    runtime.output.subscribe(console)
    runtime.coordinator.start_server("survival")
    assert wait_until(lambda: runtime.coordinator.state is ServerState.RUNNING)

    assert runtime.coordinator.stop_server() is True

    assert runtime.output.flush(WAIT)
    assert "Saved the world" in console.texts()
    assert runtime.coordinator.status().last_failure is None


def test_ignored_stop_times_out_without_kill_then_explicit_kill_works(
    runtime: ServerRuntime, root: Path, tmp_path: Path
) -> None:
    create(runtime, "stubborn", make_jar(tmp_path, "stubborn.jar", "ignore_stop=1"))
    runtime.coordinator.start_server("stubborn")
    assert wait_until(lambda: runtime.coordinator.state is ServerState.RUNNING)

    with pytest.raises(ServerStopTimedOut):
        runtime.coordinator.stop_server(timeout=0.5)
    status = runtime.coordinator.status()
    assert status.state is ServerState.STOPPING and status.stop_timed_out
    assert status.active_server_id == "stubborn"  # still running: nothing was killed

    assert runtime.coordinator.kill_server() is True

    assert runtime.coordinator.state is ServerState.STOPPED
    assert not marker(root, "stubborn").exists()  # MCServer observed the exit


def test_crash_while_running_is_diagnosed(runtime: ServerRuntime, root: Path, tmp_path: Path) -> None:
    create(runtime, "unstable", make_jar(tmp_path, "unstable.jar", "crash_after=0.5 exit_code=137"))
    runtime.coordinator.start_server("unstable")

    assert wait_until(lambda: runtime.coordinator.active_server_id is None)
    failure = runtime.coordinator.status().last_failure
    assert failure is not None
    assert failure.kind is FailureKind.UNEXPECTED_EXIT
    assert failure.hint is FailureHint.OUT_OF_MEMORY
    assert any("OutOfMemoryError" in line for line in failure.output_tail)
    assert not marker(root, "unstable").exists()


def test_unexpected_exit_during_startup_releases_the_reservation(runtime: ServerRuntime, tmp_path: Path) -> None:
    create(runtime, "broken", make_jar(tmp_path, "broken.jar", "crash-on-start"))

    runtime.coordinator.start_server("broken")

    assert wait_until(lambda: runtime.coordinator.active_server_id is None)
    failure = runtime.coordinator.take_failure("broken")
    assert failure is not None and failure.exit_code == 3
    assert "Failed to start the minecraft server" in failure.output_tail

    create(runtime, "survival", make_jar(tmp_path, "paper.jar", "normal"))
    runtime.coordinator.start_server("survival")
    assert wait_until(lambda: runtime.coordinator.state is ServerState.RUNNING)
    assert runtime.coordinator.stop_server() is True


def test_leftover_marker_is_reported_once_on_the_next_launch(root: Path, tmp_path: Path, fake_java: Path) -> None:
    with build_server_runtime(root, FakeJavaResolver(fake_java), launch_from_configuration_store=True) as runtime:
        create(runtime, "survival", make_jar(tmp_path, "paper.jar", "normal"))
    # Simulate MCServer ending while the server ran: the marker stays behind.
    marker(root, "survival").parent.mkdir(parents=True, exist_ok=True)
    marker(root, "survival").write_text('{"server_id": "survival", "started_at": "2026-11-15T09:00:00+00:00"}')

    with build_server_runtime(root, FakeJavaResolver(fake_java), launch_from_configuration_store=True) as runtime:
        incidents = runtime.health.unclean_shutdowns()
        assert [(i.server_id, i.started_at) for i in incidents] == [("survival", "2026-11-15T09:00:00+00:00")]
        runtime.health.acknowledge("survival")
        assert runtime.health.unclean_shutdowns() == ()


def test_failed_launches_leave_the_coordinator_stopped_and_reusable(
    root: Path, tmp_path: Path, fake_java: Path
) -> None:
    missing_java = FakeJavaResolver(tmp_path / "no-such-java.exe")
    with build_server_runtime(root, missing_java, launch_from_configuration_store=True) as runtime:
        create(runtime, "survival", make_jar(tmp_path, "paper.jar", "normal"))

        with pytest.raises(ServerStartFailed):
            runtime.coordinator.start_server("survival")  # Java executable cannot be started
        assert runtime.coordinator.state is ServerState.STOPPED

        with pytest.raises(ServerStartFailed):
            runtime.coordinator.start_server("unknown")  # no such configuration
        assert runtime.coordinator.state is ServerState.STOPPED

    with build_server_runtime(root, FakeJavaResolver(fake_java), launch_from_configuration_store=True) as runtime:
        runtime.coordinator.start_server("survival")
        assert wait_until(lambda: runtime.coordinator.state is ServerState.RUNNING)
        assert runtime.coordinator.stop_server() is True


def test_default_runtime_still_launches_from_legacy_file_only(root: Path, tmp_path: Path, fake_java: Path) -> None:
    """Documents the transition state: servers created in the new store need the opt-in flag (ADR 0009 later)."""
    with build_server_runtime(root, FakeJavaResolver(fake_java)) as runtime:
        create(runtime, "survival", make_jar(tmp_path, "paper.jar", "normal"))

        with pytest.raises(ServerStartFailed) as error:
            runtime.coordinator.start_server("survival")

        assert isinstance(error.value.__cause__, ServerConfigurationError)
        assert runtime.coordinator.state is ServerState.STOPPED
