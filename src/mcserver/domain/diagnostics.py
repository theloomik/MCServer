"""Recognise common Minecraft start failures from the last console lines."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum


class FailureHint(str, Enum):
    """A known cause of a failed or interrupted start; each maps to a user message."""

    EULA_NOT_ACCEPTED = "eula_not_accepted"
    PORT_IN_USE = "port_in_use"
    JAVA_TOO_OLD = "java_too_old"
    OUT_OF_MEMORY = "out_of_memory"
    CORRUPT_JAR = "corrupt_jar"
    UNKNOWN = "unknown"


# First match wins, so more specific patterns come first. Patterns are compared lower-case.
_PATTERNS: tuple[tuple[FailureHint, tuple[str, ...]], ...] = (
    (FailureHint.EULA_NOT_ACCEPTED, ("you need to agree to the eula",)),
    (
        FailureHint.JAVA_TOO_OLD,
        ("unsupportedclassversionerror", "has been compiled by a more recent version of the java runtime"),
    ),
    (
        FailureHint.PORT_IN_USE,
        ("failed to bind to port", "address already in use", "java.net.bindexception"),
    ),
    (
        FailureHint.OUT_OF_MEMORY,
        ("java.lang.outofmemoryerror", "could not reserve enough space", "insufficient memory for the java runtime"),
    ),
    (
        FailureHint.CORRUPT_JAR,
        ("invalid or corrupt jarfile", "unable to access jarfile", "zip end header not found", "zipexception"),
    ),
)


def diagnose(lines: Iterable[str]) -> FailureHint:
    """Return the first known failure pattern found in ``lines``, or ``UNKNOWN``."""
    lowered = [line.lower() for line in lines]
    for hint, patterns in _PATTERNS:
        if any(pattern in line for line in lowered for pattern in patterns):
            return hint
    return FailureHint.UNKNOWN
