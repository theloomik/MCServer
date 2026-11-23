"""Where players on the local network connect to a server (M3-GUI-05)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from mcserver.application.server_properties import ServerPropertiesService

_logger = logging.getLogger(__name__)

DEFAULT_PORT = 25565


@dataclass(frozen=True, slots=True)
class ServerAddress:
    """The address to type in Minecraft's *Direct Connection*."""

    host: str
    """This computer's LAN address, or the ``server-ip`` the server is bound to."""
    port: int

    def __str__(self) -> str:
        """Return ``host`` or ``host:port`` (the port is left out when it is the default)."""
        return self.host if self.port == DEFAULT_PORT else f"{self.host}:{self.port}"


class ServerAddressLookup:
    """Combine ``server.properties`` with this computer's LAN address."""

    def __init__(self, properties: ServerPropertiesService, lan_host: Callable[[], str | None]) -> None:
        """Read ports through ``properties``; ``lan_host`` returns the local network address, if any."""
        self._properties = properties
        self._lan_host = lan_host

    def address(self, server_id: str) -> ServerAddress | None:
        """Return the LAN address of ``server_id``, or ``None`` when this computer has no network address."""
        try:
            values = self._properties.load(server_id).values
        except Exception:
            _logger.debug("Could not read server.properties of %r.", server_id, exc_info=True)
            values = {}
        port_text = values.get("server-port", "").strip()
        port = int(port_text) if port_text.isdigit() and 0 < int(port_text) < 65536 else DEFAULT_PORT
        bound = values.get("server-ip", "").strip()
        host = bound or self._lan_host()
        return ServerAddress(host, port) if host else None
