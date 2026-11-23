"""Use case: CPU, memory and uptime of the running server (M3-BE-02)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from mcserver.application.ports import ServerConfigurationRepository
from mcserver.domain.lifecycle import ServerState


@dataclass(frozen=True, slots=True)
class ProcessSample:
    """Resource use of a server's process tree at one moment."""

    cpu_percent: float
    """Share of the whole machine (0–100), not of one core."""
    memory_bytes: int
    """Resident memory of the process and its children."""


class ProcessMetricsSource(Protocol):
    """Measure a process tree; ``None`` when the process is gone."""

    def sample(self, process_id: int) -> ProcessSample | None:
        """Return the current resource use of ``process_id`` and its children."""


@dataclass(frozen=True, slots=True)
class ActiveProcess:
    """The process of the active server, as the coordinator knows it."""

    server_id: str
    process_id: int
    state: ServerState
    started_at: float
    """Monotonic clock time the process started."""


class ActiveProcessSource(Protocol):
    """The coordinator's view of the active process."""

    def active_process(self) -> ActiveProcess | None:
        """Return the active server's process, if one runs."""


@dataclass(frozen=True, slots=True)
class ServerMetricsSnapshot:
    """What the monitoring tiles show."""

    server_id: str
    state: ServerState
    cpu_percent: float
    memory_mb: float
    allocated_mb: int
    uptime_seconds: int


class ServerMetrics:
    """Sample the active server; the GUI calls ``sample`` every couple of seconds while it runs."""

    def __init__(
        self,
        processes: ActiveProcessSource,
        source: ProcessMetricsSource,
        repository: ServerConfigurationRepository,
        clock: Callable[[], float],
    ) -> None:
        """Combine the coordinator's process, the OS measurements and the configured memory."""
        self._processes = processes
        self._source = source
        self._repository = repository
        self._clock = clock

    def sample(self) -> ServerMetricsSnapshot | None:
        """Return the active server's metrics, or ``None`` when no server process runs."""
        active = self._processes.active_process()
        if active is None:
            return None
        measured = self._source.sample(active.process_id)
        if measured is None:
            return None
        try:
            allocated = self._repository.get(active.server_id).memory_mb
        except Exception:
            allocated = 0
        return ServerMetricsSnapshot(
            server_id=active.server_id,
            state=active.state,
            cpu_percent=round(measured.cpu_percent, 1),
            memory_mb=round(measured.memory_bytes / (1024 * 1024), 1),
            allocated_mb=allocated,
            uptime_seconds=max(0, int(self._clock() - active.started_at)),
        )
