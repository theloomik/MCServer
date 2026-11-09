"""Read-only adapter for legacy server launch configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcserver.application.ports import ServerRunner
from mcserver.infrastructure.process_runner import MinecraftProcessConfig, SubprocessServerRunner


class ServerConfigurationError(ValueError):
    """Raised when a selected server has no safe, usable launch configuration."""


@dataclass(frozen=True, slots=True)
class ServerLaunchSettings:
    """The read-only launch settings required to run one configured server."""

    server_id: str
    server_jar_path: Path
    working_directory: Path
    memory_megabytes: int


class LegacyServerConfigurationRepository:
    """Read existing MCServer ``servers_config.json`` data without modifying it."""

    def __init__(self, servers_directory: Path) -> None:
        """Use the directory that owns the legacy server configuration file."""
        self._servers_directory = servers_directory.resolve()
        self._config_path = self._servers_directory / "servers_config.json"

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
        """Require a configured directory that is an immediate child of the servers root."""
        if not isinstance(value, str) or not value:
            raise ServerConfigurationError(f"Server '{server_id}' has no directory.")
        directory = Path(value).resolve()
        if directory.parent != self._servers_directory:
            raise ServerConfigurationError(f"Server '{server_id}' directory is outside the managed root.")
        return directory

    @staticmethod
    def _jar_path(entry: dict[str, Any], directory: Path) -> Path:
        """Resolve the configured JAR and keep it inside the selected server directory."""
        value = entry.get("jar_path") or entry.get("core_name")
        if not isinstance(value, str) or not value:
            raise ServerConfigurationError("Server configuration has no JAR path.")
        jar_path = Path(value)
        if not jar_path.is_absolute():
            jar_path = directory / jar_path
        jar_path = jar_path.resolve()
        if jar_path.parent != directory or jar_path.suffix.lower() != ".jar":
            raise ServerConfigurationError("Server JAR must be directly inside its server directory.")
        return jar_path

    @staticmethod
    def _memory_megabytes(value: object) -> int:
        """Normalize legacy RAM settings to the supported launch range."""
        try:
            memory = int(value)
        except (TypeError, ValueError) as error:
            raise ServerConfigurationError("Server RAM must be an integer.") from error
        return min(max(memory, 512), 262144)


class ConfiguredServerRunnerFactory:
    """Create subprocess runners from stored server settings and an explicit Java path."""

    def __init__(self, repository: LegacyServerConfigurationRepository, java_executable: str) -> None:
        """Use ``java_executable`` for each runner created from repository settings."""
        self._repository = repository
        self._java_executable = java_executable

    def create(self, server_id: str) -> ServerRunner:
        """Create a runner with conventional Minecraft memory arguments and ``nogui``."""
        settings = self._repository.get_launch_settings(server_id)
        config = MinecraftProcessConfig(
            java_executable=self._java_executable,
            jvm_arguments=(f"-Xms{settings.memory_megabytes}M", f"-Xmx{settings.memory_megabytes}M"),
            server_jar_path=settings.server_jar_path,
            working_directory=settings.working_directory,
            server_arguments=("nogui",),
        )
        return SubprocessServerRunner(config)
