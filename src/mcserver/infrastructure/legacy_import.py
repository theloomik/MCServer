"""Explicit, repeatable import of legacy ``servers_config.json`` entries.

Legacy entry (keyed by server name)::

    "survival": {
        "name": "survival", "core_name": "paper.jar",
        "jar_path": "<root>/survival/paper.jar", "ram": 4096, "directory": "<root>/survival"
    }

maps to ``ServerConfiguration(server_id="survival", directory="survival",
jar_file="paper.jar", memory_mb=4096)``. Validation and RAM clamping reuse
``LegacyServerConfigurationRepository``, so imported data matches exactly what
the legacy launcher accepts. The legacy file is only read, never modified.
"""

from __future__ import annotations

from dataclasses import dataclass

from mcserver.application.errors import ServerConfigurationAlreadyExists, ServerDirectoryInUse
from mcserver.application.ports import ServerConfigurationRepository
from mcserver.domain.errors import InvalidServerConfiguration
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.server_configuration import (
    LegacyServerConfigurationRepository,
    ServerConfigurationError,
)


@dataclass(frozen=True, slots=True)
class LegacyImportReport:
    """Outcome of one import run, by server identifier."""

    imported: tuple[str, ...]
    already_present: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]
    """``(server_id, reason)`` for entries that could not be converted or stored."""


class LegacyServerConfigurationImporter:
    """Copy legacy server entries into the new repository on explicit request.

    Running the import again is safe: servers whose ``server_id`` already
    exists in the target are reported as already present and never overwritten.
    Invalid legacy entries are reported and skipped. A corrupt or unreadable
    legacy file, or a target storage failure, stops the run with an exception;
    entries stored before that point remain and a later run continues.
    """

    def __init__(self, legacy: LegacyServerConfigurationRepository, target: ServerConfigurationRepository) -> None:
        """Import from ``legacy`` into ``target``."""
        self._legacy = legacy
        self._target = target

    def import_all(self) -> LegacyImportReport:
        """Import every legacy entry that is valid and not yet in the target."""
        present = {configuration.server_id for configuration in self._target.list_all()}
        imported: list[str] = []
        already_present: list[str] = []
        rejected: list[tuple[str, str]] = []

        for server_id in self._legacy.list_server_ids():
            if server_id in present:
                already_present.append(server_id)
                continue
            try:
                configuration = self._convert(server_id)
                self._target.add(configuration)
            except ServerConfigurationAlreadyExists:
                already_present.append(server_id)
                continue
            except (ServerConfigurationError, InvalidServerConfiguration, ServerDirectoryInUse) as error:
                rejected.append((server_id, str(error)))
                continue
            imported.append(server_id)
            present.add(server_id)

        return LegacyImportReport(tuple(imported), tuple(already_present), tuple(rejected))

    def _convert(self, server_id: str) -> ServerConfiguration:
        """Turn one validated legacy entry into a configuration with relative names."""
        settings = self._legacy.get_launch_settings(server_id)
        return ServerConfiguration(
            server_id=server_id,
            directory=settings.working_directory.name,
            jar_file=settings.server_jar_path.name,
            memory_mb=settings.memory_megabytes,
        )
