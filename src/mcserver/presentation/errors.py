"""Turn backend exceptions into user-facing messages; independent of Qt."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from mcserver.application.errors import ActiveServerAlreadyExists, ServerStartFailed, ServerStopFailed


@dataclass(frozen=True, slots=True)
class UserMessage:
    """A message key with parameters for the catalog, plus untranslated technical details."""

    key: str
    params: Mapping[str, object] = field(default_factory=dict)
    details: str = ""


def describe_error(error: BaseException) -> UserMessage:
    """Map an exception to a message; unknown errors get a generic message with details."""
    details = technical_details(error)
    if isinstance(error, ActiveServerAlreadyExists):
        return UserMessage("errors.another_server_running", {"server_id": error.active_server_id}, details)
    if isinstance(error, ServerStartFailed):
        return UserMessage("errors.start_failed", {"server_id": error.server_id}, details)
    if isinstance(error, ServerStopFailed):
        return UserMessage("errors.stop_failed", {"server_id": error.server_id}, details)
    return UserMessage("errors.unexpected", {}, details)


def technical_details(error: BaseException) -> str:
    """Return ``Type: message`` for the error and each cause, outermost first."""
    parts: list[str] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current)
        parts.append(f"{type(current).__name__}: {text}" if text else type(current).__name__)
        current = current.__cause__ or current.__context__
    return "\n".join(parts)
