"""Recognise player and tick-rate lines in Minecraft server output (M3-BE-04).

Only lines the server prints by itself or in answer to commands the user
typed are read; MCServer never sends commands to collect these values.
Examples (Vanilla and Paper)::

    [12:00:00] [Server thread/INFO]: Steve joined the game
    [12:00:09] [Server thread/INFO]: Steve left the game
    [12:00:10] [Server thread/INFO]: There are 1 of a max of 20 players online: Steve
    [12:00:10 INFO]: There are 1 out of maximum 20 players online.
    [12:00:11 INFO]: TPS from last 1m, 5m, 15m: 20.0, 19.98, *20.0
    [12:00:00] [Server thread/INFO]: Starting minecraft server version 1.21.11
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|§.")
_MESSAGE = re.compile(r"^\[[^\]]*\](?: \[[^\]]*\])?:? (?P<message>.*)$")
_NAME = r"(?P<name>\.?[A-Za-z0-9_]{1,16})"  # Bedrock players via Geyser/Floodgate get a "." prefix
_JOINED = re.compile(rf"^{_NAME} joined the game$")
_LEFT = re.compile(rf"^{_NAME} left the game$")
_LIST_VANILLA = re.compile(r"^There are (?P<count>\d+) of a max of (?P<max>\d+) players online:\s*(?P<names>.*)$")
_LIST_PAPER = re.compile(r"^There (?:are|is) (?P<count>\d+) out of maximum (?P<max>\d+) players? online\.?$")
_TPS = re.compile(r"^TPS from last 1m, 5m, 15m: \*?(?P<tps>\d+(?:\.\d+)?)")
_STARTING = re.compile(r"^Starting minecraft server version ")


class ActivityKind(str, Enum):
    """What an output line says about the server."""

    STARTING = "starting"
    JOINED = "joined"
    LEFT = "left"
    PLAYER_LIST = "player_list"
    TPS = "tps"


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    """One recognised line."""

    kind: ActivityKind
    name: str = ""
    count: int | None = None
    maximum: int | None = None
    names: tuple[str, ...] | None = None
    """Names from a Vanilla ``list`` answer; ``None`` when the line does not include them (Paper)."""
    tps: float | None = None


def _message(line: str) -> str:
    text = _ANSI_ESCAPE.sub("", line).strip()
    match = _MESSAGE.match(text)
    return match.group("message").strip() if match else text


def parse_activity_line(line: str) -> ActivityEvent | None:
    """Return what ``line`` says about players or tick rate, or ``None``."""
    message = _message(line)
    if match := _JOINED.match(message):
        return ActivityEvent(ActivityKind.JOINED, name=match.group("name"))
    if match := _LEFT.match(message):
        return ActivityEvent(ActivityKind.LEFT, name=match.group("name"))
    if match := _LIST_VANILLA.match(message):
        names = tuple(name.strip() for name in match.group("names").split(",") if name.strip())
        return ActivityEvent(
            ActivityKind.PLAYER_LIST, count=int(match.group("count")), maximum=int(match.group("max")), names=names
        )
    if match := _LIST_PAPER.match(message):
        return ActivityEvent(ActivityKind.PLAYER_LIST, count=int(match.group("count")), maximum=int(match.group("max")))
    if match := _TPS.match(message):
        return ActivityEvent(ActivityKind.TPS, tps=min(20.0, float(match.group("tps"))))
    if _STARTING.match(message):
        return ActivityEvent(ActivityKind.STARTING)
    return None
