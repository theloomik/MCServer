"""Pure rules that decide when a Minecraft server is ready for players."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

ReadinessRule = Callable[[str], bool]
"""Return whether one console line (ANSI codes may be present) shows that the server is ready."""

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\-_]|\[[0-?]*[ -/]*[@-~])")

# Vanilla, Paper, Purpur, Spigot, Fabric and Forge all log the same line once the
# world is loaded and the server accepts connections, e.g.
#   [12:00:00] [Server thread/INFO]: Done (3.456s)! For help, type "help"
_DONE_LINE = re.compile(r"\bDone \(\d+(?:[.,]\d+)?s\)! For help, type \"help\"")


def done_line_rule(line: str) -> bool:
    """Match the ``Done (…s)! For help, type "help"`` line every common server type prints."""
    return _DONE_LINE.search(_ANSI_ESCAPE.sub("", line)) is not None


DEFAULT_READINESS_RULES: tuple[ReadinessRule, ...] = (done_line_rule,)


def is_ready_line(line: str, rules: Sequence[ReadinessRule] = DEFAULT_READINESS_RULES) -> bool:
    """Return whether any readiness rule matches ``line``; new server types add a rule."""
    return any(rule(line) for rule in rules)
