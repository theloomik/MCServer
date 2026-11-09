"""Versioned JSON file storage for MCServer 2.0 server configurations.

File: ``<servers root>/server_configurations.json``::

    {
      "format_version": 1,
      "servers": [
        {"server_id": "survival", "directory": "survival", "jar_file": "paper.jar", "memory_mb": 4096}
      ]
    }

Only what cannot be derived is stored: paths are relative to the servers root,
and runtime state, JVM arguments and the Java executable are never persisted.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from threading import Lock
from typing import Any

from mcserver.application.errors import (
    ServerConfigurationAlreadyExists,
    ServerConfigurationNotFound,
    ServerConfigurationStorageError,
    ServerDirectoryInUse,
)
from mcserver.application.ports import ServerConfigurationRepository
from mcserver.domain.errors import InvalidServerConfiguration
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.server_configuration import ServerConfigurationError, ServerLaunchSettings

CONFIGURATION_FILE_NAME = "server_configurations.json"
FORMAT_VERSION = 1

_TOP_LEVEL_FIELDS = frozenset({"format_version", "servers"})
_SERVER_FIELDS = ("server_id", "directory", "jar_file", "memory_mb")


class ServerConfigurationFileError(ServerConfigurationStorageError):
    """The configuration file could not be read or written."""


class CorruptServerConfigurationFile(ServerConfigurationFileError):
    """The configuration file exists but does not contain valid version-1 data."""


class UnsupportedServerConfigurationFormat(ServerConfigurationFileError):
    """The configuration file uses a format version this application cannot read."""

    def __init__(self, path: Path, version: int) -> None:
        """Describe the unsupported version found in ``path``."""
        self.version = version
        super().__init__(
            f"{path.name} uses format version {version}; this application supports version {FORMAT_VERSION}."
        )


class ServerConfigurationWriteFailed(ServerConfigurationFileError):
    """Writing the configuration file failed; the previous file content is unchanged."""


class JsonServerConfigurationRepository:
    """Store server configurations in one versioned JSON file.

    Reads are strict: if any part of an existing file is invalid, every
    operation raises ``CorruptServerConfigurationFile`` (or
    ``UnsupportedServerConfigurationFormat``) and nothing is written, so a
    damaged or newer file is never overwritten. A missing file means no
    servers; it is created on the first write.

    Writes go to a temporary file in the same directory, are flushed to disk
    and then atomically replace the old file. Operations are serialised within
    this process; concurrent writers in other processes are not coordinated.
    """

    def __init__(self, servers_directory: Path) -> None:
        """Use ``servers_directory`` as the root that holds the configuration file."""
        self._servers_directory = servers_directory.resolve()
        self._path = self._servers_directory / CONFIGURATION_FILE_NAME
        self._lock = Lock()

    @property
    def path(self) -> Path:
        """Return the configuration file location."""
        return self._path

    def list_all(self) -> tuple[ServerConfiguration, ...]:
        """Return every stored configuration in file order."""
        with self._lock:
            return tuple(self._load().values())

    def get(self, server_id: str) -> ServerConfiguration:
        """Return the configuration stored for ``server_id``."""
        with self._lock:
            configurations = self._load()
        try:
            return configurations[server_id]
        except KeyError:
            raise ServerConfigurationNotFound(server_id) from None

    def add(self, configuration: ServerConfiguration) -> None:
        """Store a configuration for a new server."""
        with self._lock:
            configurations = self._load()
            if configuration.server_id in configurations:
                raise ServerConfigurationAlreadyExists(configuration.server_id)
            self._require_free_directory(configurations, configuration)
            configurations[configuration.server_id] = configuration
            self._save(configurations)

    def update(self, configuration: ServerConfiguration) -> None:
        """Replace the stored configuration with the same ``server_id``."""
        with self._lock:
            configurations = self._load()
            if configuration.server_id not in configurations:
                raise ServerConfigurationNotFound(configuration.server_id)
            self._require_free_directory(configurations, configuration)
            configurations[configuration.server_id] = configuration
            self._save(configurations)

    def remove(self, server_id: str) -> None:
        """Delete the configuration stored for ``server_id``."""
        with self._lock:
            configurations = self._load()
            if configurations.pop(server_id, None) is None:
                raise ServerConfigurationNotFound(server_id)
            self._save(configurations)

    @staticmethod
    def _require_free_directory(
        configurations: dict[str, ServerConfiguration], configuration: ServerConfiguration
    ) -> None:
        """Reject a directory that another server already uses."""
        wanted = configuration.directory.casefold()
        for other in configurations.values():
            if other.server_id != configuration.server_id and other.directory.casefold() == wanted:
                raise ServerDirectoryInUse(configuration.directory, other.server_id)

    def _load(self) -> dict[str, ServerConfiguration]:
        """Read and validate the whole file; a missing file holds no servers."""
        try:
            # utf-8-sig tolerates a byte-order mark added by hand-editing tools.
            text = self._path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            return {}
        except UnicodeDecodeError as error:
            raise CorruptServerConfigurationFile(f"{self._path.name} is not valid UTF-8 text.") from error
        except OSError as error:
            raise ServerConfigurationFileError(f"Could not read {self._path}.") from error
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise CorruptServerConfigurationFile(f"{self._path.name} is not valid JSON: {error}") from error
        return self._parse(data)

    def _parse(self, data: Any) -> dict[str, ServerConfiguration]:
        """Convert decoded JSON into configurations, rejecting anything unexpected."""
        if not isinstance(data, dict):
            raise self._corrupt("the top level must be a JSON object")
        version = data.get("format_version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise self._corrupt("'format_version' must be an integer")
        if version != FORMAT_VERSION:
            raise UnsupportedServerConfigurationFormat(self._path, version)
        unknown = set(data) - _TOP_LEVEL_FIELDS
        if unknown:
            raise self._corrupt(f"unknown top-level fields {sorted(unknown)}")
        servers = data.get("servers")
        if not isinstance(servers, list):
            raise self._corrupt("'servers' must be a list")

        configurations: dict[str, ServerConfiguration] = {}
        for index, entry in enumerate(servers):
            configuration = self._parse_server(index, entry)
            if configuration.server_id in configurations:
                raise self._corrupt(f"duplicate server_id {configuration.server_id!r}")
            try:
                self._require_free_directory(configurations, configuration)
            except ServerDirectoryInUse as error:
                raise self._corrupt(str(error)) from error
            configurations[configuration.server_id] = configuration
        return configurations

    def _parse_server(self, index: int, entry: Any) -> ServerConfiguration:
        """Validate one entry of the ``servers`` list."""
        if not isinstance(entry, dict):
            raise self._corrupt(f"servers[{index}] must be an object")
        missing = [field for field in _SERVER_FIELDS if field not in entry]
        unknown = sorted(set(entry) - set(_SERVER_FIELDS))
        if missing or unknown:
            raise self._corrupt(f"servers[{index}] has missing fields {missing} or unknown fields {unknown}")
        try:
            return ServerConfiguration(
                server_id=entry["server_id"],
                directory=entry["directory"],
                jar_file=entry["jar_file"],
                memory_mb=entry["memory_mb"],
            )
        except InvalidServerConfiguration as error:
            raise self._corrupt(f"servers[{index}]: {error}") from error

    def _corrupt(self, reason: str) -> CorruptServerConfigurationFile:
        return CorruptServerConfigurationFile(f"{self._path.name} is invalid: {reason}.")

    def _save(self, configurations: dict[str, ServerConfiguration]) -> None:
        """Atomically replace the file with ``configurations``."""
        payload = {
            "format_version": FORMAT_VERSION,
            "servers": [
                {
                    "server_id": configuration.server_id,
                    "directory": configuration.directory,
                    "jar_file": configuration.jar_file,
                    "memory_mb": configuration.memory_mb,
                }
                for configuration in configurations.values()
            ],
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        temporary: Path | None = None
        try:
            self._servers_directory.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(
                prefix=f".{CONFIGURATION_FILE_NAME}.", suffix=".tmp", dir=self._servers_directory
            )
            temporary = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
                file.write(text)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self._path)
        except OSError as error:
            raise ServerConfigurationWriteFailed(f"Could not write {self._path}.") from error
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)


class StoredServerLaunchSettings:
    """Derive launch settings for the process runner from stored configurations."""

    def __init__(self, repository: ServerConfigurationRepository, servers_directory: Path) -> None:
        """Resolve stored relative paths against ``servers_directory``."""
        self._repository = repository
        self._servers_directory = servers_directory.resolve()

    def get_launch_settings(self, server_id: str) -> ServerLaunchSettings:
        """Return absolute launch paths, refusing a directory that resolves outside the root."""
        configuration = self._repository.get(server_id)
        directory = (self._servers_directory / configuration.directory).resolve()
        if directory.parent != self._servers_directory:
            raise ServerConfigurationError(f"Server '{server_id}' directory resolves outside the managed root.")
        return ServerLaunchSettings(
            server_id=configuration.server_id,
            server_jar_path=directory / configuration.jar_file,
            working_directory=directory,
            memory_megabytes=configuration.memory_mb,
        )
