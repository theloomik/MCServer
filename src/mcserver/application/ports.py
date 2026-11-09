"""Application ports implemented by infrastructure adapters."""

from typing import Protocol


class ServerStarter(Protocol):
    """Accept a request to start a specific Minecraft server."""

    def start(self, server_id: str) -> None:
        """Request that ``server_id`` be started without exposing process details."""
