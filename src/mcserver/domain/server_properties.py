"""Rules for ``server.properties`` values (M3-BE-01).

Known keys get typed validation; any other key is accepted as a single line
of text, because servers and plugins add their own. Values never contain
line breaks, which would inject extra properties.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from mcserver.domain.errors import InvalidServerConfiguration
from mcserver.domain.server_configuration import is_safe_name


class PropertyKind(str, Enum):
    """How a known property is edited and validated."""

    BOOLEAN = "boolean"
    INTEGER = "integer"
    PORT = "port"
    CHOICE = "choice"
    TEXT = "text"
    WORLD_NAME = "world_name"


@dataclass(frozen=True, slots=True)
class PropertySpec:
    """The editor and limits of one known property."""

    kind: PropertyKind
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()


_BOOLEAN = PropertySpec(PropertyKind.BOOLEAN)
_PORT = PropertySpec(PropertyKind.PORT, 1, 65535)

KNOWN_PROPERTIES: Mapping[str, PropertySpec] = {
    "server-port": _PORT,
    "query.port": _PORT,
    "rcon.port": _PORT,
    "server-ip": PropertySpec(PropertyKind.TEXT),
    "motd": PropertySpec(PropertyKind.TEXT),
    "level-name": PropertySpec(PropertyKind.WORLD_NAME),
    "level-seed": PropertySpec(PropertyKind.TEXT),
    "gamemode": PropertySpec(PropertyKind.CHOICE, choices=("survival", "creative", "adventure", "spectator")),
    "difficulty": PropertySpec(PropertyKind.CHOICE, choices=("peaceful", "easy", "normal", "hard")),
    "max-players": PropertySpec(PropertyKind.INTEGER, 0, 2147483647),
    "view-distance": PropertySpec(PropertyKind.INTEGER, 2, 32),
    "simulation-distance": PropertySpec(PropertyKind.INTEGER, 2, 32),
    "spawn-protection": PropertySpec(PropertyKind.INTEGER, 0, 2147483647),
    "max-world-size": PropertySpec(PropertyKind.INTEGER, 1, 29999984),
    "player-idle-timeout": PropertySpec(PropertyKind.INTEGER, 0, 2147483647),
    "online-mode": _BOOLEAN,
    "pvp": _BOOLEAN,
    "hardcore": _BOOLEAN,
    "white-list": _BOOLEAN,
    "enforce-whitelist": _BOOLEAN,
    "allow-flight": _BOOLEAN,
    "allow-nether": _BOOLEAN,
    "spawn-monsters": _BOOLEAN,
    "enable-command-block": _BOOLEAN,
    "enable-rcon": _BOOLEAN,
    "enable-query": _BOOLEAN,
    "force-gamemode": _BOOLEAN,
}


class InvalidServerProperties(InvalidServerConfiguration):
    """Raised when one or more property values are invalid; ``problems`` maps keys to reasons."""

    def __init__(self, problems: Mapping[str, str]) -> None:
        """Describe every invalid value at once, so the editor can mark all of them."""
        self.problems = dict(problems)
        details = "; ".join(f"{key}: {reason}" for key, reason in self.problems.items())
        super().__init__(f"Invalid server properties: {details}")


def _is_property_key(key: str) -> bool:
    return bool(key) and key == key.strip() and not any(character in key for character in "=:#!\r\n\t ")


def normalize_property(key: str, value: str) -> str:
    """Return the value to store for ``key``; raise ``ValueError`` with a reason if it is invalid."""
    if not _is_property_key(key):
        raise ValueError("invalid property name")
    if "\n" in value or "\r" in value:
        raise ValueError("must be a single line")
    spec = KNOWN_PROPERTIES.get(key)
    if spec is None or spec.kind is PropertyKind.TEXT:
        return value
    text = value.strip()
    if spec.kind is PropertyKind.BOOLEAN:
        if text.lower() not in ("true", "false"):
            raise ValueError("must be true or false")
        return text.lower()
    if spec.kind is PropertyKind.CHOICE:
        if text.lower() not in spec.choices:
            raise ValueError(f"must be one of {', '.join(spec.choices)}")
        return text.lower()
    if spec.kind is PropertyKind.WORLD_NAME:
        if not is_safe_name(text):
            raise ValueError("must be a simple folder name")
        return text
    try:
        number = int(text)
    except ValueError:
        raise ValueError("must be a whole number") from None
    if (spec.minimum is not None and number < spec.minimum) or (spec.maximum is not None and number > spec.maximum):
        raise ValueError(f"must be between {spec.minimum} and {spec.maximum}")
    return str(number)


def validate_properties(changes: Mapping[str, str]) -> dict[str, str]:
    """Normalize every change or raise ``InvalidServerProperties`` listing all problems."""
    normalized: dict[str, str] = {}
    problems: dict[str, str] = {}
    for key, value in changes.items():
        try:
            normalized[key] = normalize_property(key, value)
        except ValueError as error:
            problems[key] = str(error)
    if problems:
        raise InvalidServerProperties(problems)
    return normalized
