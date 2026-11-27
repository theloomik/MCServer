"""Subprocess-backed Minecraft server runner."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from subprocess import PIPE, Popen, TimeoutExpired  # nosec B404
from threading import Lock, Thread
from typing import IO

from mcserver.application.errors import ProcessGuardUnavailable, ServerCommandFailed
from mcserver.application.ports import OutputStream, ProcessExitHandler, ProcessOutputHandler, ServerOutputSink
from mcserver.infrastructure.windows_job import NoProcessGuard, ProcessGuard

DEFAULT_DIAGNOSTIC_LINE_LIMIT = 1000
KILL_WAIT_SECONDS = 10.0

_logger = logging.getLogger(__name__)


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
    """Run one configured Minecraft process and report its output and exit asynchronously.

    The runner reports events only; lifecycle states belong to the coordinator
    (ADR 0005). ``stop`` is always graceful and never kills (ADR 0006); ``kill``
    is a separate, explicit operation. Each output line is kept in small
    diagnostic buffers and, when an ``output_sink`` is given, forwarded to it
    from the reader thread before the exit callback runs. Commands sent with
    ``send_command`` are echoed to the sink as ``OutputStream.COMMAND`` lines.
    """

    def __init__(
        self,
        config: MinecraftProcessConfig,
        output_sink: ServerOutputSink | None = None,
        diagnostic_line_limit: int = DEFAULT_DIAGNOSTIC_LINE_LIMIT,
        process_guard: ProcessGuard | None = None,
    ) -> None:
        """Create a runner for a single immutable process configuration."""
        if diagnostic_line_limit < 1:
            raise ValueError("Diagnostic line limit must be at least 1.")
        self._config = config
        self._output_sink = output_sink
        self._guard: ProcessGuard = process_guard or NoProcessGuard()
        self._process: Popen[str] | None = None
        self._server_id: str | None = None
        self._return_code: int | None = None
        self._stdout_lines: deque[str] = deque(maxlen=diagnostic_line_limit)
        self._stderr_lines: deque[str] = deque(maxlen=diagnostic_line_limit)
        self._all_lines: deque[str] = deque(maxlen=diagnostic_line_limit)
        self._lock = Lock()
        self._stdin_lock = Lock()
        self._reader_threads: list[Thread] = []

    @property
    def process_id(self) -> int | None:
        """Return the operating-system process identifier after a successful launch."""
        with self._lock:
            return self._process.pid if self._process is not None else None

    @property
    def running(self) -> bool:
        """Return whether the started process has not exited yet."""
        with self._lock:
            process = self._process
        return process is not None and process.poll() is None

    @property
    def return_code(self) -> int | None:
        """Return the process exit code after it has terminated."""
        with self._lock:
            return self._return_code

    @property
    def command(self) -> tuple[str, ...]:
        """Return the configured shell-free command for diagnostics and verification."""
        return self._config.command()

    @property
    def stdout_lines(self) -> tuple[str, ...]:
        """Return the most recent captured standard-output lines."""
        with self._lock:
            return tuple(self._stdout_lines)

    @property
    def stderr_lines(self) -> tuple[str, ...]:
        """Return the most recent captured standard-error lines."""
        with self._lock:
            return tuple(self._stderr_lines)

    def output_tail(self, limit: int = 40) -> tuple[str, ...]:
        """Return the last ``limit`` lines of stdout and stderr in arrival order."""
        with self._lock:
            lines = tuple(self._all_lines)
        return lines[-limit:] if limit > 0 else ()

    def start(self, server_id: str, on_exit: ProcessExitHandler, on_output: ProcessOutputHandler | None = None) -> None:
        """Start the process (guarded against orphaning) and report output and exit from background threads."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise ProcessAlreadyRunning("The configured server process is already running.")
            self._return_code = None
            self._server_id = server_id
            self._stdout_lines.clear()
            self._stderr_lines.clear()
            self._all_lines.clear()
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
                    creationflags=self._guard.creation_flags,
                )
            except (FileNotFoundError, PermissionError, OSError) as error:
                raise ProcessStartError("Could not start the configured Minecraft process.") from error

            try:
                self._guard.protect(process.pid)
            except ProcessGuardUnavailable:
                # The guard terminated the process before it ran any code; reap it.
                self._reap(process)
                raise

            self._process = process
            self._reader_threads = [
                self._start_reader(process.stdout, self._stdout_lines, OutputStream.STDOUT, server_id, on_output),
                self._start_reader(process.stderr, self._stderr_lines, OutputStream.STDERR, server_id, on_output),
            ]
            Thread(target=self._wait_for_exit, args=(process, on_exit), daemon=True).start()

    def send_command(self, command: str) -> None:
        """Write one command line to the server's console and echo it to the output sink."""
        with self._lock:
            process = self._process
            server_id = self._server_id or ""
        if process is None or process.poll() is not None or process.stdin is None:
            raise ServerCommandFailed(server_id)
        with self._stdin_lock:
            try:
                process.stdin.write(command + "\n")
                process.stdin.flush()
            except (OSError, ValueError) as error:
                raise ServerCommandFailed(server_id) from error
        self._forward(server_id, OutputStream.COMMAND, command)

    def stop(self, timeout: float) -> bool:
        """Send Minecraft's ``stop`` command and wait up to ``timeout``; never force termination."""
        if timeout < 0:
            raise ValueError("Shutdown timeout must not be negative.")
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return True
        if process.stdin is not None:
            with self._stdin_lock:
                try:
                    process.stdin.write("stop\n")
                    process.stdin.flush()
                except (OSError, ValueError):
                    pass  # input already closed: the process is exiting; waiting tells
        return self.wait_for_exit(timeout)

    def wait_for_exit(self, timeout: float) -> bool:
        """Wait up to ``timeout`` seconds; return whether the process has exited."""
        with self._lock:
            process = self._process
        if process is None:
            return True
        try:
            process.wait(timeout=timeout)
        except TimeoutExpired:
            return False
        return True

    def kill(self) -> None:
        """Terminate the process immediately (explicit user decision) and wait briefly for it."""
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            process.kill()
        except OSError:
            if process.poll() is None:
                raise
        try:
            process.wait(timeout=KILL_WAIT_SECONDS)
        except TimeoutExpired:
            _logger.warning("Process %s did not end within %s s after kill.", process.pid, KILL_WAIT_SECONDS)

    def _start_reader(
        self,
        stream: IO[str] | None,
        lines: deque[str],
        kind: OutputStream,
        server_id: str,
        on_output: ProcessOutputHandler | None,
    ) -> Thread:
        """Start a daemon reader that drains one process stream."""
        thread = Thread(target=self._read_stream, args=(stream, lines, kind, server_id, on_output), daemon=True)
        thread.start()
        return thread

    def _read_stream(
        self,
        stream: IO[str] | None,
        lines: deque[str],
        kind: OutputStream,
        server_id: str,
        on_output: ProcessOutputHandler | None,
    ) -> None:
        """Drain a text stream until EOF so child processes cannot block on output."""
        if stream is None:
            return
        try:
            for raw_line in stream:
                text = raw_line.rstrip("\r\n")
                with self._lock:
                    lines.append(text)
                    self._all_lines.append(text)
                self._forward(server_id, kind, text)
                if on_output is not None:
                    try:
                        on_output(kind, text)
                    except Exception:
                        _logger.exception("Server output handler failed.")
        finally:
            stream.close()

    def _forward(self, server_id: str, kind: OutputStream, text: str) -> None:
        """Publish one line to the sink; a failing sink must never stop stream draining."""
        if self._output_sink is None:
            return
        try:
            self._output_sink.publish(server_id, kind, text)
        except Exception:
            _logger.exception("Server output sink failed.")

    def _wait_for_exit(self, process: Popen[str], on_exit: ProcessExitHandler) -> None:
        """Wait for process completion, join readers, then publish the exit code once.

        The guard is released before joining the readers: closing the job ends
        any child the server left behind, which would otherwise keep the output
        pipes open and the readers waiting.
        """
        return_code = process.wait()
        self._guard.release()
        for reader in self._reader_threads:
            reader.join()
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        with self._lock:
            if self._process is not process:
                return
            self._return_code = return_code
        on_exit(return_code)

    @staticmethod
    def _reap(process: Popen[str]) -> None:
        """Collect a process that was terminated before it ran and close its pipes."""
        try:
            process.wait(timeout=KILL_WAIT_SECONDS)
        except TimeoutExpired:
            _logger.warning("Process %s did not end after the guard terminated it.", process.pid)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
