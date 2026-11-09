"""Application ports implemented by infrastructure adapters."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

ProcessExitHandler = Callable[[int], None]


class OutputStream(Enum):
    """The process stream a console line was read from."""

    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass(frozen=True, slots=True)
class ServerOutputLine:
    """One console line produced by a server process.

    ``sequence`` increases monotonically per output buffer so consumers can
    order lines and discard duplicates after a replay.
    """

    sequence: int
    server_id: str
    stream: OutputStream
    text: str


ServerOutputListener = Callable[[ServerOutputLine], None]


class ServerOutputSink(Protocol):
    """Receive console lines from a running server process."""

    def publish(self, server_id: str, stream: OutputStream, text: str) -> None:
        """Record one console line without its trailing newline."""


class ServerRunner(Protocol):
    """Start and stop a server process without exposing process APIs to use cases."""

    def start(self, server_id: str, on_exit: ProcessExitHandler) -> None:
        """Start ``server_id`` and notify ``on_exit`` once its process exits."""

    def stop(self, timeout: float) -> None:
        """Request graceful shutdown, forcing termination after ``timeout`` seconds."""


class ServerRunnerFactory(Protocol):
    """Create a runner configured for a selected server."""

    def create(self, server_id: str) -> ServerRunner:
        """Return a new runner configured for ``server_id``."""
