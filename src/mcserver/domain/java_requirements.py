"""Which Java major version a Minecraft release needs, for verified releases only.

The table was checked on 2026-11-14 against ``javaVersion.majorVersion`` in
Mojang's version metadata for every release from 1.16 up to ``26.3``. A
version newer than ``HIGHEST_VERIFIED_VERSION`` (or one that cannot be parsed,
such as a snapshot) has an *unknown* requirement: callers must warn instead of
assuming one.
"""

from __future__ import annotations

import re

MinecraftVersion = tuple[int, ...]

HIGHEST_VERIFIED_VERSION: MinecraftVersion = (26, 3)

# (first release of the range, required Java major), ascending.
_REQUIREMENTS: tuple[tuple[MinecraftVersion, int], ...] = (
    ((1, 0), 8),
    ((1, 17), 16),
    ((1, 18), 17),
    ((1, 20, 5), 21),
    ((26, 1), 25),
)

_RELEASE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")


def parse_minecraft_version(text: str) -> MinecraftVersion | None:
    """Parse a release id such as ``1.21.11`` or ``26.1.2``; anything else (snapshots, pre-releases) is ``None``."""
    match = _RELEASE.match(text.strip())
    if match is None:
        return None
    parts = tuple(int(part) for part in match.groups() if part is not None)
    return _normalized(parts)


def required_java_major(version: MinecraftVersion | None) -> int | None:
    """Return the Java major ``version`` needs, or ``None`` when it is unknown or unverified."""
    if version is None:
        return None
    version = _normalized(version)
    if version > _normalized(HIGHEST_VERIFIED_VERSION) or version < (1, 0, 0):
        return None
    required: int | None = None
    for first, major in _REQUIREMENTS:
        if version >= _normalized(first):
            required = major
    return required


def _normalized(version: MinecraftVersion) -> MinecraftVersion:
    """Pad to three parts so ``1.20`` and ``1.20.0`` compare equal."""
    return (*version, 0, 0, 0)[:3]
