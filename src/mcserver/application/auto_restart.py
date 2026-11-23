"""Opt-in automatic restart after a crash, with a limit (M3-BE-05)."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from mcserver.application.server_coordinator import FailureKind, ServerFailure

MAX_RESTARTS = 3
WINDOW_SECONDS = 600.0
RESTART_DELAY_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class RestartDecision:
    """Whether to restart after a failure, and which attempt this is."""

    restart: bool
    attempt: int
    """1-based attempt number within the window (when ``restart``)."""
    gave_up: bool = False
    """Auto-restart is on, but the limit was reached; the user has to look at the crash."""


class AutoRestartPolicy:
    """Decide whether a crashed server is started again.

    Only an unexpected exit counts as a crash. A server that did not become
    ready in time, or that the user stopped or killed, is never restarted.
    At most ``max_restarts`` restarts happen within ``window_seconds``; after
    that the server stays stopped so a crash loop does not hide the problem.
    """

    def __init__(
        self,
        enabled: Callable[[], bool],
        *,
        max_restarts: int = MAX_RESTARTS,
        window_seconds: float = WINDOW_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """Ask ``enabled`` on every failure (it follows the application settings)."""
        self._enabled = enabled
        self._max_restarts = max_restarts
        self._window = window_seconds
        self._clock = clock
        self._lock = Lock()
        self._history: dict[str, deque[float]] = {}

    @property
    def max_restarts(self) -> int:
        """Return the number of restarts allowed within the window."""
        return self._max_restarts

    def decide(self, failure: ServerFailure) -> RestartDecision:
        """Return whether to restart ``failure.server_id`` now, and record the attempt."""
        if failure.kind is not FailureKind.UNEXPECTED_EXIT or not self._enabled():
            return RestartDecision(False, 0)
        now = self._clock()
        with self._lock:
            history = self._history.setdefault(failure.server_id, deque())
            while history and now - history[0] > self._window:
                history.popleft()
            if len(history) >= self._max_restarts:
                return RestartDecision(False, len(history), gave_up=True)
            history.append(now)
            return RestartDecision(True, len(history))

    def reset(self, server_id: str) -> None:
        """Forget earlier restarts (the user started or stopped the server)."""
        with self._lock:
            self._history.pop(server_id, None)
