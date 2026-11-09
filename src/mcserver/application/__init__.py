"""Use cases that coordinate domain objects and infrastructure abstractions."""

from mcserver.application.errors import (
    ActiveServerAlreadyExists,
    LegacyConfigurationUnavailable,
    LegacyServerEntryInvalid,
    ServerConfigurationAlreadyExists,
    ServerConfigurationNotFound,
    ServerConfigurationStorageError,
    ServerDirectoryInUse,
    ServerStartFailed,
    ServerStopFailed,
)
from mcserver.application.ports import (
    LegacyServerConfigurationSource,
    OutputStream,
    ServerConfigurationRepository,
    ServerOutputLine,
    ServerOutputSink,
)
from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_management import LegacyImportResult, RejectedLegacyServer, ServerManagement
from mcserver.application.server_output import ServerOutputBuffer

__all__ = [
    "ActiveServerAlreadyExists",
    "LegacyConfigurationUnavailable",
    "LegacyImportResult",
    "LegacyServerConfigurationSource",
    "LegacyServerEntryInvalid",
    "OutputStream",
    "RejectedLegacyServer",
    "ServerConfigurationAlreadyExists",
    "ServerConfigurationNotFound",
    "ServerConfigurationRepository",
    "ServerConfigurationStorageError",
    "ServerCoordinator",
    "ServerDirectoryInUse",
    "ServerManagement",
    "ServerOutputBuffer",
    "ServerOutputLine",
    "ServerOutputSink",
    "ServerStartFailed",
    "ServerStopFailed",
]
