"""File-based session markers that reveal an unclean shutdown on the next launch (M1-BE-08)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from mcserver.application.ports import ServerConfigurationRepository, SessionMarker

MARKER_DIRECTORY = ".mcserver"
MARKER_FILE = "running"

_logger = logging.getLogger(__name__)


class FileSessionMarkerStore:
    """Keep ``<server directory>/.mcserver/running`` while a server process runs.

    The marker is written atomically when the process starts and deleted when
    the application observes its exit. It survives anything that ends the
    application first (crash, forced end, power loss), so its presence on the
    next launch identifies the affected server. Only this marker file is ever
    deleted; the server's other files are not touched.
    """

    def __init__(self, servers_directory: Path, repository: ServerConfigurationRepository) -> None:
        """Map server identifiers to directories through ``repository``."""
        self._servers_directory = servers_directory.resolve()
        self._repository = repository

    def write(self, server_id: str, process_id: int | None) -> None:
        """Record that ``server_id`` is running."""
        path = self._marker_path(server_id)
        path.parent.mkdir(exist_ok=True)
        payload = {
            "server_id": server_id,
            "process_id": process_id,
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        temporary = path.with_name(f".{MARKER_FILE}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def clear(self, server_id: str) -> None:
        """Delete ``server_id``'s marker if it exists."""
        try:
            path = self._marker_path(server_id)
        except LookupError:
            return  # the server no longer exists, so there is nothing to clear
        path.unlink(missing_ok=True)

    def leftovers(self) -> tuple[SessionMarker, ...]:
        """Return the markers of configured servers that are present on disk."""
        found: list[SessionMarker] = []
        for configuration in self._repository.list_all():
            path = self._directory(configuration.directory) / MARKER_DIRECTORY / MARKER_FILE
            if not path.is_file():
                continue
            started_at = ""
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("started_at"), str):
                    started_at = data["started_at"]
            except (OSError, ValueError):
                _logger.warning("Unreadable session marker for %r; reporting it anyway.", configuration.server_id)
            found.append(SessionMarker(configuration.server_id, started_at))
        return tuple(found)

    def _marker_path(self, server_id: str) -> Path:
        configuration = self._repository.get(server_id)
        return self._directory(configuration.directory) / MARKER_DIRECTORY / MARKER_FILE

    def _directory(self, directory: str) -> Path:
        path = (self._servers_directory / directory).resolve()
        if path.parent != self._servers_directory:
            raise LookupError(f"Server directory '{directory}' resolves outside the servers root.")
        return path
