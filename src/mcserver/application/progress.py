"""Progress and cooperative cancellation for long operations (M4-BE-02).

Use cases take a ``ProgressReporter`` (called with ``Progress``: a stage key,
units done, units total) and a ``CancelToken``. Storage adapters keep simple
``(done, total)`` callbacks; ``stage_callback`` adapts between the two and
raises ``OperationCancelled`` inside the adapter's loop once cancel was asked,
so the adapter's own cleanup removes partial results.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from threading import Event


class Stage(str, Enum):
    """What a long operation is doing now; the GUI shows ``progress.stage.<value>``."""

    COPYING = "copying"
    SAVING_WORLD = "saving_world"
    ARCHIVING = "archiving"
    SAFETY_BACKUP = "safety_backup"
    EXTRACTING = "extracting"
    IMPORTING = "importing"
    EXPORTING = "exporting"
    DOWNLOADING = "downloading"


@dataclass(frozen=True, slots=True)
class Progress:
    """One progress report; ``total`` 0 means the amount is unknown (show a busy indicator)."""

    stage: Stage
    done: int = 0
    total: int = 0

    @property
    def fraction(self) -> float | None:
        """Return 0–1, or ``None`` when the total is unknown."""
        if self.total <= 0:
            return None
        return max(0.0, min(1.0, self.done / self.total))


ProgressReporter = Callable[[Progress], None]
UnitCallback = Callable[[int, int], None]
"""The low-level ``(done, total)`` callback storage adapters call."""


class OperationCancelled(RuntimeError):
    """The user cancelled the operation; its partial results were removed."""


class CancelToken:
    """Thread-safe flag the GUI sets and a worker checks between units of work."""

    def __init__(self) -> None:
        """Start not cancelled."""
        self._event = Event()

    def cancel(self) -> None:
        """Ask the operation to stop at its next check."""
        self._event.set()

    @property
    def cancelled(self) -> bool:
        """Return whether cancel was asked."""
        return self._event.is_set()

    def check(self) -> None:
        """Raise ``OperationCancelled`` when cancel was asked."""
        if self._event.is_set():
            raise OperationCancelled()


def report(reporter: ProgressReporter | None, stage: Stage, done: int = 0, total: int = 0) -> None:
    """Send one report if there is a reporter."""
    if reporter is not None:
        reporter(Progress(stage, done, total))


def stage_callback(stage: Stage, reporter: ProgressReporter | None, cancel: CancelToken | None) -> UnitCallback:
    """Return a ``(done, total)`` callback for an adapter: it checks ``cancel`` and reports ``stage``."""

    def callback(done: int, total: int) -> None:
        if cancel is not None:
            cancel.check()
        report(reporter, stage, done, total)

    return callback


__all__ = [
    "CancelToken",
    "OperationCancelled",
    "Progress",
    "ProgressReporter",
    "Stage",
    "UnitCallback",
    "report",
    "stage_callback",
]
