"""Windows-only tests of orphan protection with real processes and a real Job Object (M1-BE-06)."""

from __future__ import annotations

import subprocess  # nosec B404
import sys
import time
from pathlib import Path
from threading import Event

import pytest

from mcserver.application.errors import ProcessGuardUnavailable
from mcserver.infrastructure.process_runner import MinecraftProcessConfig, SubprocessServerRunner

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Job Objects exist only on Windows")

if sys.platform == "win32":
    from mcserver.infrastructure.windows_job import CREATE_SUSPENDED, Win32JobApi, WindowsJobGuard

FLAG_SCRIPT = (
    "import os, sys, time\n"
    "open('started.flag', 'w').write(str(os.getpid()))\n"
    "print('ready', flush=True)\n"
    "for line in sys.stdin:\n"
    "    if line.strip() == 'stop':\n"
    "        sys.exit(0)\n"
)


def config(tmp_path: Path, script: str) -> MinecraftProcessConfig:
    fake = tmp_path / "fake_java.py"
    fake.write_text(script, encoding="utf-8")
    jar = tmp_path / "server.jar"
    jar.write_bytes(b"jar")
    return MinecraftProcessConfig(sys.executable, ("-u", str(fake)), jar, tmp_path)


def process_alive(pid: int) -> bool:
    output = subprocess.run(  # nosec B603 B607
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, check=False
    ).stdout
    return str(pid) in output


def test_suspended_process_runs_no_code_until_resumed_and_is_in_the_job(tmp_path: Path) -> None:
    script = tmp_path / "flag.py"
    script.write_text(FLAG_SCRIPT, encoding="utf-8")
    process = subprocess.Popen(  # nosec B603
        [sys.executable, "-u", str(script)],
        cwd=tmp_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        creationflags=CREATE_SUSPENDED,
    )
    api = Win32JobApi()
    guard = WindowsJobGuard(api)
    try:
        time.sleep(0.5)
        assert not (tmp_path / "started.flag").exists()  # suspended: nothing ran yet

        guard.protect(process.pid)

        assert guard.job is not None and api.is_in_job(guard.job, process.pid)
        deadline = time.monotonic() + 5
        while not (tmp_path / "started.flag").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert (tmp_path / "started.flag").exists()
    finally:
        process.kill()
        process.wait(5)
        guard.release()


class FailingAssignApi:
    """The real API, except that assignment fails."""

    def __init__(self) -> None:
        self.real = Win32JobApi()

    def __getattr__(self, name: str) -> object:
        return getattr(self.real, name)

    def assign(self, job: int, process_id: int) -> None:
        raise OSError("simulated: access denied")


def test_failed_assignment_terminates_the_process_before_it_runs(tmp_path: Path) -> None:
    runner = SubprocessServerRunner(config(tmp_path, FLAG_SCRIPT), process_guard=WindowsJobGuard(FailingAssignApi()))  # type: ignore[arg-type]

    with pytest.raises(ProcessGuardUnavailable):
        runner.start("survival", lambda _code: None)

    time.sleep(0.5)
    assert not (tmp_path / "started.flag").exists()
    assert runner.process_id is None and not runner.running


def test_guarded_runner_starts_stops_and_releases_the_job(tmp_path: Path) -> None:
    guard = WindowsJobGuard()
    runner = SubprocessServerRunner(config(tmp_path, FLAG_SCRIPT), process_guard=guard)
    exited = Event()

    runner.start("survival", lambda _code: exited.set())

    assert guard.job is not None
    assert runner.stop(timeout=5) is True
    assert exited.wait(5)
    assert guard.job is None


HELPER = r"""
import sys, time
sys.path[:0] = [{src!r}]
from pathlib import Path
from mcserver.infrastructure.process_runner import MinecraftProcessConfig, SubprocessServerRunner
from mcserver.infrastructure.windows_job import WindowsJobGuard

workdir = Path({workdir!r})
config = MinecraftProcessConfig({python!r}, ("-u", {script!r}), workdir / "server.jar", workdir)
runner = SubprocessServerRunner(config, process_guard=WindowsJobGuard())
runner.start("survival", lambda _code: None)
print(runner.process_id, flush=True)
time.sleep(60)
"""


def test_server_dies_with_mcserver_when_mcserver_is_terminated(tmp_path: Path) -> None:
    """MCServer ending without running any code (End task) must not leave the server running."""
    script = tmp_path / "server_script.py"
    script.write_text("import time\nprint('ready', flush=True)\ntime.sleep(60)\n", encoding="utf-8")
    (tmp_path / "server.jar").write_bytes(b"jar")
    src = str(Path(__file__).resolve().parents[3] / "src")
    helper = tmp_path / "mcserver_stand_in.py"
    helper.write_text(
        HELPER.format(src=src, workdir=str(tmp_path), python=sys.executable, script=str(script)), encoding="utf-8"
    )
    stand_in = subprocess.Popen([sys.executable, "-u", str(helper)], stdout=subprocess.PIPE, text=True)  # nosec B603
    try:
        assert stand_in.stdout is not None
        server_pid = int(stand_in.stdout.readline().strip())
        assert process_alive(server_pid)

        stand_in.kill()  # TerminateProcess: no MCServer code runs
        stand_in.wait(5)

        deadline = time.monotonic() + 5
        while process_alive(server_pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not process_alive(server_pid)
    finally:
        if stand_in.poll() is None:
            stand_in.kill()
