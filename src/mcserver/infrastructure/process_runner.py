"""Subprocess-backed Minecraft server runner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from subprocess import PIPE, Popen, TimeoutExpired  # nosec B404
from threading import Lock, Thread
from typing import TextIO

from mcserver.application.ports import ProcessExitHandler
from mcserver.domain.lifecycle import ServerState


class InvalidProcessConfiguration(ValueError):
    """Raised when a process runner configuration is incomplete."""


class ProcessStartError(RuntimeError):
    """Raised when the operating system cannot start the configured process."""


class ProcessAlreadyRunning(RuntimeError):
    """Raised when a runner receives a second start request before process exit."""


@dataclass(frozen=True, slots=True)
class MinecraftProcessConfig:
    """Command-line configuration for one Minecraft Java server process."""

    java_executable: str
    jvm_arguments: tuple[str, ...]
    server_jar_path: Path
    working_directory: Path
    server_arguments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject empty command components before attempting a process launch."""
        if not self.java_executable.strip():
            raise InvalidProcessConfiguration("A Java executable is required.")
        if not str(self.server_jar_path).strip():
            raise InvalidProcessConfiguration("A server JAR path is required.")
        if not str(self.working_directory).strip():
            raise InvalidProcessConfiguration("A working directory is required.")

    def command(self) -> tuple[str, ...]:
        """Build the Java command without invoking a shell."""
        return (
            self.java_executable,
            *self.jvm_arguments,
            "-jar",
            str(self.server_jar_path),
            *self.server_arguments,
        )


class SubprocessServerRunner:
    """Run one configured Minecraft process and report its exit asynchronously."""

    def __init__(self, config: MinecraftProcessConfig) -> None:
        """Create a runner for a single immutable process configuration."""
        self._config = config
        self._process: Popen[str] | None = None
        self._state = ServerState.STOPPED
        self._return_code: int | None = None
        self._stdout_lines: list[str] = []
        self._stderr_lines: list[str] = []
        self._lock = Lock()
        self._reader_threads: list[Thread] = []

    @property
    def state(self) -> ServerState:
        """Return the runner's current process state."""
        with self._lock:
            return self._state

    @property
    def process_id(self) -> int | None:
        """Return the operating-system process identifier after a successful launch."""
        with self._lock:
            return self._process.pid if self._process is not None else None

    @property
    def return_code(self) -> int | None:
        """Return the process exit code after it has terminated."""
        with self._lock:
            return self._return_code

    @property
    def stdout_lines(self) -> tuple[str, ...]:
        """Return all captured standard-output lines observed so far."""
        with self._lock:
            return tuple(self._stdout_lines)

    @property
    def stderr_lines(self) -> tuple[str, ...]:
        """Return all captured standard-error lines observed so far."""
        with self._lock:
            return tuple(self._stderr_lines)

    def start(self, _server_id: str, on_exit: ProcessExitHandler) -> None:
        """Start the configured process and notify ``on_exit`` from a waiter thread."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise ProcessAlreadyRunning("The configured server process is already running.")
            self._state = ServerState.STARTING
            self._return_code = None
            self._stdout_lines.clear()
            self._stderr_lines.clear()
            try:
                # The command is a sequence and shell execution is never used.
                process = Popen(  # nosec B603
                    self._config.command(),
                    cwd=self._config.working_directory,
                    stdin=PIPE,
                    stdout=PIPE,
                    stderr=PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except (FileNotFoundError, PermissionError, OSError) as error:
                self._state = ServerState.STOPPED
                raise ProcessStartError("Could not start the configured Minecraft process.") from error

            self._process = process
            self._state = ServerState.RUNNING
            self._reader_threads = [
                self._start_reader(process.stdout, self._stdout_lines),
                self._start_reader(process.stderr, self._stderr_lines),
            ]
            Thread(target=self._wait_for_exit, args=(process, on_exit), daemon=True).start()

    def stop(self, timeout: float) -> None:
        """Send Minecraft's stop command, then force termination after ``timeout``."""
        if timeout < 0:
            raise ValueError("Shutdown timeout must not be negative.")
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                return
            self._state = ServerState.STOPPING
            stdin = process.stdin

        if stdin is not None:
            try:
                stdin.write("stop\n")
                stdin.flush()
            except OSError:
                pass
        try:
            process.wait(timeout=timeout)
        except TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except TimeoutExpired:
                process.kill()
                process.wait()

    def _start_reader(self, stream: TextIO | None, lines: list[str]) -> Thread:
        """Start a daemon reader that drains one process stream."""
        thread = Thread(target=self._read_stream, args=(stream, lines), daemon=True)
        thread.start()
        return thread

    def _read_stream(self, stream: TextIO | None, lines: list[str]) -> None:
        """Drain a text stream until EOF so child processes cannot block on output."""
        if stream is None:
            return
        try:
            for line in stream:
                with self._lock:
                    lines.append(line.rstrip("\r\n"))
        finally:
            stream.close()

    def _wait_for_exit(self, process: Popen[str], on_exit: Callable[[int], None]) -> None:
        """Wait for process completion, join readers, then publish the exit code once."""
        return_code = process.wait()
        for reader in self._reader_threads:
            reader.join()
        with self._lock:
            if self._process is not process:
                return
            self._return_code = return_code
            self._state = ServerState.STOPPED
        on_exit(return_code)
