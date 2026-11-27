"""Read-only adapter that exposes legacy ``servers_config.json`` entries for import.

Legacy entry (keyed by server name)::

    "survival": {
        "name": "survival", "core_name": "paper.jar",
        "jar_path": "<root>/survival/paper.jar", "ram": 4096, "directory": "<root>/survival"
    }

maps to ``ServerConfiguration(server_id="survival", directory="survival",
jar_file="paper.jar", memory_mb=4096)``. Validation and RAM clamping reuse
``LegacyServerConfigurationRepository``, so imported data matches exactly what
the legacy launcher accepts. The legacy file is only read, never modified.
The import policy itself lives in ``ServerManagement.import_legacy_servers``.
"""

from __future__ import annotations

from mcserver.application.errors import LegacyConfigurationUnavailable, LegacyServerEntryInvalid
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.server_configuration import (
    LegacyServerConfigurationRepository,
    ServerConfigurationError,
)


class LegacyFileServerConfigurationSource:
    """Implement ``LegacyServerConfigurationSource`` over the legacy JSON file."""

    def __init__(self, legacy: LegacyServerConfigurationRepository) -> None:
        """Read entries through the existing read-only legacy repository."""
        self._legacy = legacy

    def list_server_ids(self) -> tuple[str, ...]:
        """Return legacy server identifiers; empty when the legacy file does not exist."""
        try:
            return self._legacy.list_server_ids()
        except ServerConfigurationError as error:
            raise LegacyConfigurationUnavailable(str(error)) from error

    def read_server(self, server_id: str) -> ServerConfiguration:
        """Convert one validated legacy entry into a configuration with relative names."""
        try:
            settings = self._legacy.get_launch_settings(server_id)
        except ServerConfigurationError as error:
            raise LegacyServerEntryInvalid(server_id, str(error)) from error
        return ServerConfiguration(
            server_id=server_id,
            directory=settings.working_directory.name,
            jar_file=settings.server_jar_path.name,
            memory_mb=settings.memory_megabytes,
        )
