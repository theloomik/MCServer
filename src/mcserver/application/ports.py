"""Application ports implemented by infrastructure adapters."""

from collections.abc import Callable
from typing import Protocol

ProcessExitHandler = Callable[[int], None]


class ServerRunner(Protocol):
    """Start and stop a server process without exposing process APIs to use cases."""

    def start(self, server_id: str, on_exit: ProcessExitHandler) -> None:
        """Start ``server_id`` and notify ``on_exit`` once its process exits."""

    def stop(self, timeout: float) -> None:
        """Request graceful shutdown, forcing termination after ``timeout`` seconds."""
