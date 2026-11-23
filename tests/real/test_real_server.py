"""Optional smoke test with a real Minecraft server JAR and a real Java (M1-QA-04).

Skipped unless ``MCSERVER_TEST_JAR`` points to a Vanilla or Paper server JAR::

    $env:MCSERVER_TEST_JAR = "C:\\path\\to\\paper-1.21.11-130.jar"
    uv run pytest -m real_minecraft

The JAR is copied into a temporary servers folder (a ``cache`` folder next to
it is copied too, so Paper does not need to download the Vanilla JAR). The
server runs on a free local port with a fresh world. Expect 1–3 minutes.
"""

from __future__ import annotations

import os
import shutil
import socket
import time
from pathlib import Path

import pytest

from mcserver.application.ports import OutputStream, ServerOutputLine
from mcserver.bootstrap.server_runtime import build_server_runtime
from mcserver.domain.lifecycle import ServerState

pytestmark = pytest.mark.real_minecraft

TEST_JAR = os.environ.get("MCSERVER_TEST_JAR", "")
STARTUP_TIMEOUT = 300.0
STOP_TIMEOUT = 120.0


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def wait_until(condition, timeout: float) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.2)
    return condition()


@pytest.mark.skipif(not TEST_JAR, reason="set MCSERVER_TEST_JAR to a Vanilla or Paper server JAR")
def test_real_server_creates_starts_takes_a_command_and_stops_gracefully(tmp_path: Path) -> None:
    source = Path(TEST_JAR)
    assert source.is_file(), f"MCSERVER_TEST_JAR does not exist: {source}"
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    jar = shutil.copy2(source, downloads / source.name)
    root = tmp_path / "servers"
    lines: list[ServerOutputLine] = []

    with build_server_runtime(root, startup_timeout=STARTUP_TIMEOUT, stop_timeout=STOP_TIMEOUT) as runtime:
        runtime.output.subscribe(lines.append)
        runtime.server_creation.create_server(
            server_id="smoke",
            directory="smoke",
            jar_file=source.name,
            memory_mb=2048,
            source_jar=str(jar),
            accept_eula=True,
        )
        server_directory = root / "smoke"
        if (source.parent / "cache").is_dir():
            shutil.copytree(source.parent / "cache", server_directory / "cache")
        port = free_port()
        (server_directory / "server.properties").write_text(
            f"server-port={port}\nonline-mode=false\nmotd=MCServer smoke test\n", encoding="utf-8"
        )

        report = runtime.coordinator.start_server("smoke")
        print("warnings:", report.warnings)
        assert runtime.coordinator.state is ServerState.STARTING

        assert wait_until(lambda: runtime.coordinator.state is not ServerState.STARTING, STARTUP_TIMEOUT + 30)
        texts = [line.text for line in lines]
        assert runtime.coordinator.state is ServerState.RUNNING, (runtime.coordinator.status(), texts[-30:])
        assert any("Done (" in text for text in texts)

        runtime.coordinator.send_command("smoke", "say hello from MCServer")
        assert wait_until(
            lambda: any("hello from MCServer" in line.text for line in lines if line.stream is OutputStream.STDOUT),
            30,
        )

        assert runtime.coordinator.stop_server() is True
        assert runtime.coordinator.state is ServerState.STOPPED
        assert runtime.coordinator.status().last_failure is None
        assert not (server_directory / ".mcserver" / "running").exists()
        assert (server_directory / "world" / "level.dat").is_file()  # the world was saved
