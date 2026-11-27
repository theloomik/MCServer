"""Measure a server's process tree with psutil (M3-BE-02).

``psutil.Process.cpu_percent`` needs a previous call to compare against, so
process objects are kept between samples; the first sample of a process reports
0 % CPU. CPU is normalised to the whole machine (all cores = 100 %), as Task
Manager shows it.
"""

from __future__ import annotations

from threading import Lock

import psutil

from mcserver.application.server_metrics import ProcessSample


def total_memory_mb() -> int | None:
    """Return this PC's physical memory in megabytes, or ``None`` when it cannot be read."""
    try:
        return int(psutil.virtual_memory().total // (1024 * 1024))
    except Exception:
        return None


class PsutilProcessMetrics:
    """Implement ``ProcessMetricsSource`` for a process and all of its children."""

    def __init__(self) -> None:
        """Start with no remembered processes."""
        self._processes: dict[int, psutil.Process] = {}
        self._lock = Lock()
        self._cores = psutil.cpu_count() or 1

    def sample(self, process_id: int) -> ProcessSample | None:
        """Return CPU and memory of ``process_id`` plus its children, or ``None`` if it is gone."""
        with self._lock:
            try:
                root = self._process(process_id)
                tree = [root, *root.children(recursive=True)]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self._processes.pop(process_id, None)
                return None
            cpu = 0.0
            memory = 0
            alive: set[int] = set()
            for process in tree:
                try:
                    tracked = self._process(process.pid)
                    cpu += tracked.cpu_percent(None)
                    memory += tracked.memory_info().rss
                    alive.add(process.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            for pid in set(self._processes) - alive:
                del self._processes[pid]
            return ProcessSample(min(100.0, cpu / self._cores), memory)

    def _process(self, process_id: int) -> psutil.Process:
        process = self._processes.get(process_id)
        if process is None or not process.is_running():
            process = psutil.Process(process_id)
            process.cpu_percent(None)  # prime: the next call measures from now
            self._processes[process_id] = process
        return process
