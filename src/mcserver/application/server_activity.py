"""Players online and tick rate per server, read from console output (M3-BE-04)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock

from mcserver.application.ports import OutputStream, ServerOutputLine
from mcserver.domain.server_activity import ActivityKind, parse_activity_line

_logger = logging.getLogger(__name__)

MaxPlayersSource = Callable[[str], int | None]
"""Return ``max-players`` from the server's settings, if known."""


@dataclass(frozen=True, slots=True)
class ServerActivitySnapshot:
    """What is known about players and tick rate of one server's current run."""

    server_id: str
    players: tuple[str, ...]
    """Names seen joining and not yet leaving, sorted."""
    player_count: int
    """From the last ``list`` answer when newer than the join/leave lines, else ``len(players)``."""
    max_players: int | None
    tps: float | None
    """The 1-minute tick rate from the last ``tps`` answer (Paper, Spigot), if any."""


@dataclass(slots=True)
class _Run:
    players: set[str] = field(default_factory=set)
    counted: int | None = None
    maximum: int | None = None
    tps: float | None = None


class ServerActivity:
    """Subscribe to the output buffer and keep per-server activity; thread-safe.

    A new run starts at the ``Starting minecraft server`` line, which clears
    what was known about the previous run. Values are best-effort: lines a
    plugin rewrites are not recognised, and nothing is ever sent to the
    server to collect them.
    """

    def __init__(self, max_players: MaxPlayersSource | None = None) -> None:
        """Use ``max_players`` when no ``list`` answer told the maximum."""
        self._max_players = max_players
        self._lock = Lock()
        self._runs: dict[str, _Run] = {}

    def on_line(self, line: ServerOutputLine) -> None:
        """Read one output line (an output-buffer listener)."""
        if line.stream is OutputStream.COMMAND:
            return
        event = parse_activity_line(line.text)
        if event is None:
            return
        with self._lock:
            if event.kind is ActivityKind.STARTING:
                self._runs[line.server_id] = _Run()
                return
            run = self._runs.setdefault(line.server_id, _Run())
            if event.kind is ActivityKind.JOINED:
                run.players.add(event.name)
                run.counted = None
            elif event.kind is ActivityKind.LEFT:
                run.players.discard(event.name)
                run.counted = None
            elif event.kind is ActivityKind.PLAYER_LIST:
                run.counted = event.count
                run.maximum = event.maximum
                if event.names is not None:
                    run.players = set(event.names)
            elif event.kind is ActivityKind.TPS:
                run.tps = event.tps

    def snapshot(self, server_id: str) -> ServerActivitySnapshot:
        """Return what is known about ``server_id``'s current run."""
        with self._lock:
            run = self._runs.get(server_id) or _Run()
            players = tuple(sorted(run.players, key=str.lower))
            count = run.counted if run.counted is not None else len(players)
            maximum, tps = run.maximum, run.tps
        if maximum is None and self._max_players is not None:
            try:
                maximum = self._max_players(server_id)
            except Exception:
                _logger.debug("Could not read max-players for %r.", server_id, exc_info=True)
        return ServerActivitySnapshot(server_id, players, count, maximum, tps)

    def forget(self, server_id: str) -> None:
        """Drop what is known about ``server_id`` (its server stopped)."""
        with self._lock:
            self._runs.pop(server_id, None)
