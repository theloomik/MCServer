"""Application composition root for manual dependency injection."""

from mcserver.bootstrap.server_runtime import build_server_coordinator

__all__ = ["build_server_coordinator"]
