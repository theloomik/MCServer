"""Use case: read and change a server's ``server.properties`` (M3-BE-01)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from mcserver.domain.server_properties import validate_properties


@dataclass(frozen=True, slots=True)
class ServerPropertiesDocument:
    """Decoded properties in file order; ``exists`` is false until the server first started."""

    values: Mapping[str, str]
    exists: bool


class ServerPropertiesStore(Protocol):
    """File access for one server's ``server.properties``.

    ``write`` keeps every line it does not change exactly as it was and is atomic.
    """

    def read(self, server_id: str) -> ServerPropertiesDocument:
        """Return the current properties of ``server_id``."""

    def write(self, server_id: str, changes: Mapping[str, str]) -> None:
        """Store already validated ``changes``; create the file if it does not exist yet."""


@dataclass(frozen=True, slots=True)
class ServerPropertiesView:
    """What the properties editor shows."""

    server_id: str
    values: Mapping[str, str]
    exists: bool
    running: bool
    """The server is active, so saved changes apply after a restart."""


class ServerPropertiesService:
    """Validate and store property changes; never touches lines it does not change."""

    def __init__(self, store: ServerPropertiesStore, active_server: Callable[[], str | None] = lambda: None) -> None:
        """Use ``store``; ``active_server`` tells whether a restart is needed for changes to apply."""
        self._store = store
        self._active_server = active_server

    def load(self, server_id: str) -> ServerPropertiesView:
        """Return the current properties of ``server_id``."""
        document = self._store.read(server_id)
        return ServerPropertiesView(
            server_id, dict(document.values), document.exists, self._active_server() == server_id
        )

    def save(self, server_id: str, changes: Mapping[str, str]) -> bool:
        """Validate and store ``changes``; return whether the server must restart for them to apply.

        Raises ``InvalidServerProperties`` listing every invalid value; nothing is written then.
        """
        normalized = validate_properties(changes)
        if normalized:
            self._store.write(server_id, normalized)
        return self._active_server() == server_id
