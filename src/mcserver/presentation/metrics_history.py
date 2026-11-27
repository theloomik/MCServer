"""Recent CPU and memory samples per server, for the dashboard charts (M4-GUI-06); independent of Qt."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from mcserver.application.server_metrics import ServerMetricsSnapshot

HISTORY_CAPACITY = 300
"""Samples kept per server: ten minutes at one sample every two seconds."""


@dataclass(frozen=True, slots=True)
class MetricPoint:
    """One sample of a running server."""

    cpu_percent: float
    memory_mb: float
    allocated_mb: int
    uptime_seconds: int


class MetricsHistory:
    """Keep the newest samples of each server; a restart starts a new series.

    It belongs to the application's services rather than to a window, so a
    window rebuilt for another language or theme shows the same history.
    """

    def __init__(self, capacity: int = HISTORY_CAPACITY) -> None:
        """Keep at most ``capacity`` samples per server."""
        self.capacity = capacity
        self._series: dict[str, deque[MetricPoint]] = {}

    def add(self, snapshot: ServerMetricsSnapshot) -> None:
        """Record ``snapshot``; an uptime lower than the last sample means the server was started again."""
        series = self._series.setdefault(snapshot.server_id, deque(maxlen=self.capacity))
        point = MetricPoint(snapshot.cpu_percent, snapshot.memory_mb, snapshot.allocated_mb, snapshot.uptime_seconds)
        if series and snapshot.uptime_seconds < series[-1].uptime_seconds:
            series.clear()
        elif series and snapshot.uptime_seconds == series[-1].uptime_seconds:
            # Sampled again within the same second (a selection change also samples): keep one point per moment.
            series[-1] = point
            return
        series.append(point)

    def points(self, server_id: str | None) -> tuple[MetricPoint, ...]:
        """Return the samples of ``server_id``, oldest first (none for ``None`` or an unknown server)."""
        if server_id is None:
            return ()
        return tuple(self._series.get(server_id, ()))

    def forget(self, server_id: str) -> None:
        """Drop the samples of a server (it was deleted)."""
        self._series.pop(server_id, None)


__all__ = ["HISTORY_CAPACITY", "MetricPoint", "MetricsHistory"]
