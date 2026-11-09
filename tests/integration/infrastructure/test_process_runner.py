"""Integration tests for the subprocess-backed Minecraft process runner."""

import sys
from pathlib import Path
from threading import Event
from typing import Any

import pytest

from mcserver.application.ports import OutputStream
from mcserver.application.server_output import ServerOutputBuffer
from mcserver.domain.lifecycle import ServerState
from mcserver.infrastructure.process_runner import (
    InvalidProcessConfiguration,
    MinecraftProcessConfig,
    ProcessStartError,
    SubprocessServerRunner,
)


def make_fake_java(tmp_path: Path, behavior: str) -> Path:
    """Create a Python program that acts as a controlled Java-process substitute."""
    script = tmp_path / "fake_java.py"
    script.write_text(behavior, encoding="utf-8")
    return script


class RecordingSink:
    """Collect published output lines for assertions."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, OutputStream, str]] = []

    def publish(self, server_id: str, stream: OutputStream, text: str) -> None:
        self.lines.append((server_id, stream, text))


class FailingSink:
    """A sink whose failures must not stop the runner from draining output."""

    def publish(self, server_id: str, stream: OutputStream, text: str) -> None:
        raise RuntimeError("sink bug")


def make_runner(tmp_path: Path, behavior: str, **runner_options: Any) -> SubprocessServerRunner:
    """Build a runner using Python as a deterministic fake Java executable."""
    fake_java = make_fake_java(tmp_path, behavior)
    jar = tmp_path / "server.jar"
    jar.write_bytes(b"not a real jar")
    config = MinecraftProcessConfig(
        java_executable=sys.executable,
        jvm_arguments=("-u", str(fake_java)),
        server_jar_path=jar,
        working_directory=tmp_path,
        server_arguments=("--test-mode",),
    )
    return SubprocessServerRunner(config, **runner_options)


def test_runner_uses_configured_working_directory_arguments_and_streams(tmp_path: Path) -> None:
    runner = make_runner(
        tmp_path,
        "import os, sys\n"
        "print(f'cwd={os.getcwd()}', flush=True)\n"
        "print('stderr-ready', file=sys.stderr, flush=True)\n"
        "print('args=' + '|'.join(sys.argv[1:]), flush=True)\n",
    )
    exited = Event()

    runner.start("survival", lambda _code: exited.set())

    assert exited.wait(3)
    assert runner.state is ServerState.STOPPED
    assert runner.return_code == 0
    assert f"cwd={tmp_path}" in runner.stdout_lines
    assert "stderr-ready" in runner.stderr_lines
    assert any("-jar" in line and "--test-mode" in line for line in runner.stdout_lines)


def test_runner_reports_unexpected_process_exit(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, "import sys\nprint('failed', file=sys.stderr, flush=True)\nsys.exit(7)\n")
    exited = Event()
    exit_codes: list[int] = []

    runner.start("survival", lambda code: (exit_codes.append(code), exited.set()))

    assert exited.wait(3)
    assert exit_codes == [7]
    assert runner.return_code == 7
    assert runner.state is ServerState.STOPPED
    assert runner.stderr_lines == ("failed",)


def test_runner_sends_graceful_stop_command(tmp_path: Path) -> None:
    runner = make_runner(
        tmp_path,
        "import sys\n"
        "print('ready', flush=True)\n"
        "for line in sys.stdin:\n"
        "    if line.strip() == 'stop':\n"
        "        print('stopped', flush=True)\n"
        "        sys.exit(0)\n",
    )
    exited = Event()

    runner.start("survival", lambda _code: exited.set())
    runner.stop(timeout=2)

    assert exited.wait(3)
    assert runner.return_code == 0
    assert "stopped" in runner.stdout_lines


def test_runner_forces_termination_after_timeout(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, "import time\nprint('ready', flush=True)\ntime.sleep(30)\n")
    exited = Event()

    runner.start("survival", lambda _code: exited.set())
    runner.stop(timeout=0.01)

    assert exited.wait(3)
    assert runner.return_code is not None
    assert runner.state is ServerState.STOPPED


def test_runner_reports_missing_executable_as_start_error(tmp_path: Path) -> None:
    config = MinecraftProcessConfig(
        java_executable=str(tmp_path / "missing-java"),
        jvm_arguments=(),
        server_jar_path=tmp_path / "server.jar",
        working_directory=tmp_path,
    )
    runner = SubprocessServerRunner(config)

    with pytest.raises(ProcessStartError):
        runner.start("survival", lambda _code: None)

    assert runner.state is ServerState.STOPPED


def test_runner_publishes_output_to_sink_before_reporting_exit(tmp_path: Path) -> None:
    sink = RecordingSink()
    runner = make_runner(
        tmp_path,
        "import sys\nprint('hello', flush=True)\nprint('oops', file=sys.stderr, flush=True)\n",
        output_sink=sink,
    )
    lines_at_exit: list[tuple[str, OutputStream, str]] = []
    exited = Event()

    runner.start("survival", lambda _code: (lines_at_exit.extend(sink.lines), exited.set()))

    assert exited.wait(3)
    assert sorted(lines_at_exit, key=lambda item: item[1].value) == [
        ("survival", OutputStream.STDERR, "oops"),
        ("survival", OutputStream.STDOUT, "hello"),
    ]


def test_runner_feeds_output_buffer_in_stream_order(tmp_path: Path) -> None:
    buffer = ServerOutputBuffer()
    runner = make_runner(tmp_path, "for i in range(5):\n    print(f'line {i}', flush=True)\n", output_sink=buffer)
    exited = Event()

    runner.start("survival", lambda _code: exited.set())

    assert exited.wait(3)
    assert [line.text for line in buffer.snapshot("survival")] == [f"line {i}" for i in range(5)]


def test_runner_keeps_draining_when_sink_fails(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, "for i in range(3):\n    print(i, flush=True)\n", output_sink=FailingSink())
    exited = Event()

    runner.start("survival", lambda _code: exited.set())

    assert exited.wait(3)
    assert runner.return_code == 0
    assert runner.stdout_lines == ("0", "1", "2")


def test_runner_diagnostic_buffer_is_bounded(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, "for i in range(50):\n    print(i, flush=True)\n", diagnostic_line_limit=5)
    exited = Event()

    runner.start("survival", lambda _code: exited.set())

    assert exited.wait(3)
    assert runner.stdout_lines == ("45", "46", "47", "48", "49")


def test_runner_rejects_non_positive_diagnostic_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Diagnostic line limit"):
        make_runner(tmp_path, "", diagnostic_line_limit=0)


def test_runner_rejects_empty_java_executable(tmp_path: Path) -> None:
    with pytest.raises(InvalidProcessConfiguration, match="Java executable"):
        MinecraftProcessConfig("", (), tmp_path / "server.jar", tmp_path)
