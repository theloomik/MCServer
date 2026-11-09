"""Application composition root for manual dependency injection."""

from mcserver.bootstrap.server_runtime import (
    ServerRuntime,
    build_legacy_importer,
    build_server_coordinator,
    build_server_runtime,
)

__all__ = ["ServerRuntime", "build_legacy_importer", "build_server_coordinator", "build_server_runtime"]
