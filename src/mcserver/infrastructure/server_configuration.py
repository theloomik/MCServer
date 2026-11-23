"""Read-only adapter for legacy server launch configuration."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from mcserver.application.errors import EulaNotAccepted, JavaVersionTooOld, ServerPortInUse, ServerWorldInUse
from mcserver.application.ports import (
    JavaRuntimeProvider,
    LaunchWarning,
    PreparedLaunch,
    ServerOutputSink,
    StartOptions,
)
from mcserver.domain.java_requirements import required_java_major
from mcserver.domain.server_configuration import is_safe_name
from mcserver.infrastructure.jar_version import read_jar_version
from mcserver.infrastructure.process_runner import MinecraftProcessConfig, SubprocessServerRunner
from mcserver.infrastructure.server_files import eula_file_accepted
from mcserver.infrastructure.server_properties_file import PROPERTIES_FILE, port_in_use, read_properties
from mcserver.infrastructure.windows_job import NoProcessGuard, ProcessGuard


class ServerConfigurationError(ValueError):
    """Raised when a selected server has no safe, usable launch configuration."""


@dataclass(frozen=True, slots=True)
class ServerLaunchSettings:
    """The read-only launch settings required to run one configured server."""

    server_id: str
    server_jar_path: Path
    working_directory: Path
    memory_megabytes: int
    jvm_arguments: tuple[str, ...] = ()
    java_path: str | None = None
    """A per-server Java executable that overrides detection (ADR 0007)."""


class LaunchSettingsSource(Protocol):
    """Anything that can provide validated launch settings for a server."""

    def get_launch_settings(self, server_id: str) -> ServerLaunchSettings:
        """Return launch settings for ``server_id``."""


class LegacyServerConfigurationRepository:
    """Read existing MCServer ``servers_config.json`` data without modifying it."""

    def __init__(self, servers_directory: Path) -> None:
        """Use the directory that owns the legacy server configuration file."""
        self._servers_directory = servers_directory.resolve()
        self._config_path = self._servers_directory / "servers_config.json"

    def list_server_ids(self) -> tuple[str, ...]:
        """Return the configured server identifiers; empty when the legacy file does not exist."""
        if not self._config_path.exists():
            return ()
        return tuple(self._read_config())

    def get_launch_settings(self, server_id: str) -> ServerLaunchSettings:
        """Return validated launch settings for the selected configured server."""
        if not server_id or server_id in {".", ".."}:
            raise ServerConfigurationError("A valid server identifier is required.")
        data = self._read_config()
        entry = data.get(server_id)
        if not isinstance(entry, dict):
            raise ServerConfigurationError(f"Server '{server_id}' was not found.")

        directory = self._managed_directory(entry.get("directory"), server_id)
        jar_path = self._jar_path(entry, directory)
        memory = self._memory_megabytes(entry.get("ram"))
        return ServerLaunchSettings(server_id, jar_path, directory, memory)

    def _read_config(self) -> dict[str, Any]:
        """Load the legacy JSON object without altering corrupt source data."""
        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ServerConfigurationError("Could not read server configuration.") from error
        if not isinstance(data, dict):
            raise ServerConfigurationError("Server configuration must contain an object.")
        return data

    def _managed_directory(self, value: object, server_id: str) -> Path:
        """Require a configured directory that is an immediate child of the servers root.

        MCServer 0.9.1 stored absolute paths in packaged builds but paths relative
        to its working directory in development runs (``minecraft_servers\\x``).
        A relative path is therefore taken by its last part, inside the servers
        root, so the result does not depend on the current directory.
        """
        if not isinstance(value, str) or not value:
            raise ServerConfigurationError(f"Server '{server_id}' has no directory.")
        configured = Path(value)
        directory = configured.resolve() if configured.is_absolute() else (self._servers_directory / configured.name)
        if directory.parent != self._servers_directory:
            raise ServerConfigurationError(f"Server '{server_id}' directory is outside the managed root.")
        return directory

    @staticmethod
    def _jar_path(entry: dict[str, Any], directory: Path) -> Path:
        """Return the server JAR the way MCServer 0.9.1 launched it: ``<directory>/<core_name>``.

        ``jar_path`` (where the JAR was copied from, possibly relative to the old
        working directory) only supplies the file name when ``core_name`` is
        missing. The JAR must be directly inside the server directory.
        """
        core_name = entry.get("core_name")
        jar_path_value = entry.get("jar_path")
        if isinstance(core_name, str) and core_name:
            name = core_name
        elif isinstance(jar_path_value, str) and jar_path_value:
            name = Path(jar_path_value).name
        else:
            raise ServerConfigurationError("Server configuration has no JAR path.")
        if Path(name).name != name:
            raise ServerConfigurationError("Server JAR must be directly inside its server directory.")
        jar_path = (directory / name).resolve()
        if jar_path.parent != directory or jar_path.suffix.lower() != ".jar":
            raise ServerConfigurationError("Server JAR must be directly inside its server directory.")
        return jar_path

    @staticmethod
    def _memory_megabytes(value: object) -> int:
        """Normalize legacy RAM settings to the supported launch range."""
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ServerConfigurationError("Server RAM must be an integer.")
        try:
            memory = int(value)
        except ValueError as error:
            raise ServerConfigurationError("Server RAM must be an integer.") from error
        return min(max(memory, 512), 262144)


class ConfiguredServerRunnerFactory:
    """Check launch preconditions, then create a guarded subprocess runner (M1-BE-01, 05, 06).

    Checks, in order: EULA consent (``eula=true``), the world not being locked
    by another process, and Java. The Java requirement comes from the JAR's own
    ``version.json`` when it declares one, otherwise from the verified table in
    ``domain.java_requirements``; an unknown requirement only produces a
    warning. A Java that is too old blocks the start unless
    ``StartOptions.allow_outdated_java`` is set.

    ``java`` is a ``JavaRuntimeProvider`` (looked up on every start) or a fixed
    executable path, which skips the version check (used by tests).
    """

    def __init__(
        self,
        repository: LaunchSettingsSource,
        java: JavaRuntimeProvider | str,
        output_sink: ServerOutputSink | None = None,
        process_guard_factory: Callable[[], ProcessGuard] | None = None,
        check_port: bool = True,
    ) -> None:
        """Use ``java`` and forward runner output to ``output_sink`` when given."""
        self._check_port = check_port
        self._repository = repository
        self._java = java
        self._output_sink = output_sink
        self._process_guard_factory = process_guard_factory or NoProcessGuard

    def create(self, server_id: str, options: StartOptions | None = None) -> PreparedLaunch:
        """Return a runner with conventional Minecraft memory arguments and ``nogui``."""
        options = options or StartOptions()
        settings = self._repository.get_launch_settings(server_id)
        if not eula_file_accepted(settings.working_directory):
            raise EulaNotAccepted(server_id)
        world = locked_world(settings.working_directory)
        if world is not None:
            raise ServerWorldInUse(server_id, world)
        host, port = server_address(settings.working_directory)
        if self._check_port and port_in_use(host, port):
            raise ServerPortInUse(server_id, port)
        java_executable, warnings = self._java_for(server_id, settings, options)
        config = MinecraftProcessConfig(
            java_executable=java_executable,
            jvm_arguments=(
                f"-Xms{settings.memory_megabytes}M",
                f"-Xmx{settings.memory_megabytes}M",
                *settings.jvm_arguments,
            ),
            server_jar_path=settings.server_jar_path,
            working_directory=settings.working_directory,
            server_arguments=("nogui",),
        )
        runner = SubprocessServerRunner(
            config, output_sink=self._output_sink, process_guard=self._process_guard_factory()
        )
        return PreparedLaunch(runner, warnings)

    def _java_for(
        self, server_id: str, settings: ServerLaunchSettings, options: StartOptions
    ) -> tuple[str, tuple[LaunchWarning, ...]]:
        if isinstance(self._java, str):
            return self._java, ()
        jar = read_jar_version(settings.server_jar_path)
        required = jar.declared_java_major or required_java_major(jar.version)
        java = self._java.inspect(settings.java_path) if settings.java_path else self._java.find(required)
        warnings: list[LaunchWarning] = []
        if required is None:
            warnings.append(
                LaunchWarning(
                    "java_requirement_unknown",
                    {"version": jar.version_text or "?", "java_major": java.major_version},
                )
            )
        elif java.major_version < required:
            if not options.allow_outdated_java:
                raise JavaVersionTooOld(server_id, required, java.major_version, java.executable)
            warnings.append(
                LaunchWarning("java_outdated_allowed", {"required": required, "java_major": java.major_version})
            )
        return java.executable, tuple(warnings)


def locked_world(server_directory: Path) -> str | None:
    """Return the world name if its ``session.lock`` is held by another process, else ``None``."""
    world = _level_name(server_directory)
    lock_path = server_directory / world / "session.lock"
    if not lock_path.is_file():
        return None
    try:
        handle = lock_path.open("r+b")
    except PermissionError:
        return world
    except OSError:
        return None
    with handle:
        return world if not _try_lock(handle.fileno()) else None


def _try_lock(fileno: int) -> bool:
    """Try to take and release the lock Minecraft holds on ``session.lock``."""
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fileno, msvcrt.LK_NBLCK, 1)
            msvcrt.locking(fileno, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.lockf(fileno, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.lockf(fileno, fcntl.LOCK_UN)
    except OSError:
        return False
    return True


def _level_name(server_directory: Path) -> str:
    """Return ``level-name`` from ``server.properties`` (default ``world``), if it is a safe name."""
    name = read_properties(server_directory / PROPERTIES_FILE).values.get("level-name", "world").strip()
    return name if is_safe_name(name) else "world"


DEFAULT_SERVER_PORT = 25565


def server_address(server_directory: Path) -> tuple[str, int]:
    """Return ``server-ip`` and ``server-port`` as the server will bind them (defaults: all addresses, 25565)."""
    values = read_properties(server_directory / PROPERTIES_FILE).values
    try:
        port = int(values.get("server-port", "").strip() or DEFAULT_SERVER_PORT)
    except ValueError:
        port = DEFAULT_SERVER_PORT
    return values.get("server-ip", "").strip(), port if 0 < port < 65536 else DEFAULT_SERVER_PORT
