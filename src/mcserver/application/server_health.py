"""Use case that reports servers which were not stopped cleanly in an earlier session."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from mcserver.application.ports import SessionMarkerStore

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UncleanShutdown:
    """A server whose process was still running when the application ended."""

    server_id: str
    started_at: str


class ServerHealth:
    """Find incidents from the previous session and forget them once the user saw them.

    Call ``unclean_shutdowns`` once at application start, before any server is
    started: the markers written by this session are not incidents. Recent
    world changes may be lost in such an incident; recovery from backups only
    exists once backups are implemented (M3).
    """

    def __init__(self, markers: SessionMarkerStore) -> None:
        """Read and clear markers through ``markers``."""
        self._markers = markers

    def unclean_shutdowns(self) -> tuple[UncleanShutdown, ...]:
        """Return one incident per leftover marker; unreadable storage yields none (and is logged)."""
        try:
            found = self._markers.leftovers()
        except Exception:
            _logger.exception("Could not read session markers.")
            return ()
        return tuple(UncleanShutdown(marker.server_id, marker.started_at) for marker in found)

    def acknowledge(self, server_id: str) -> None:
        """Forget the incident for ``server_id`` so it is reported only once."""
        self._markers.clear(server_id)
