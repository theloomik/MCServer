"""Turn backend exceptions into user-facing messages; independent of Qt."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from mcserver.application.errors import (
    ActiveServerAlreadyExists,
    InvalidSourceJar,
    ProvisioningRollbackFailed,
    ServerConfigurationAlreadyExists,
    ServerConfigurationStorageError,
    ServerCreationRollbackFailed,
    ServerDirectoryAlreadyExists,
    ServerDirectoryInUse,
    ServerJarAlreadyExists,
    ServerProvisioningError,
    ServerStartFailed,
    ServerStopFailed,
)
from mcserver.domain.errors import InvalidServerConfiguration


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
    creation = _describe_creation_error(error, details)
    if creation is not None:
        return creation
    return UserMessage("errors.unexpected", {}, details)


def _describe_creation_error(error: BaseException, details: str) -> UserMessage | None:
    """Messages for creating a server; rollback failures always name what was left behind."""
    if isinstance(error, ServerCreationRollbackFailed):
        leftovers = leftover_paths(error.provisioning_error)
        return UserMessage(
            "errors.creation_rollback_failed",
            {"server_id": error.server_id, "leftovers": ", ".join(leftovers) or "-"},
            details,
        )
    if isinstance(error, ProvisioningRollbackFailed):
        return UserMessage(
            "errors.provisioning_rollback_failed",
            {"server_id": error.server_id, "leftovers": ", ".join(error.leftovers) or "-"},
            details,
        )
    if isinstance(error, ServerConfigurationAlreadyExists):
        return UserMessage("errors.server_id_taken", {"server_id": error.server_id}, details)
    if isinstance(error, ServerDirectoryInUse):
        return UserMessage(
            "errors.directory_in_use", {"directory": error.directory, "server_id": error.owner_server_id}, details
        )
    if isinstance(error, ServerDirectoryAlreadyExists):
        return UserMessage("errors.directory_exists", {"directory": error.directory}, details)
    if isinstance(error, ServerJarAlreadyExists):
        return UserMessage("errors.jar_exists", {"directory": error.directory, "jar_file": error.jar_file}, details)
    if isinstance(error, InvalidSourceJar):
        return UserMessage("errors.invalid_source_jar", {"reason": error.reason}, details)
    if isinstance(error, InvalidServerConfiguration):
        return UserMessage("errors.invalid_configuration", {"reason": str(error)}, details)
    if isinstance(error, ServerProvisioningError):
        return UserMessage("errors.provisioning_failed", {}, details)
    if isinstance(error, ServerConfigurationStorageError):
        return UserMessage("errors.storage_failed", {}, details)
    return None


def leftover_paths(error: BaseException) -> tuple[str, ...]:
    """Return paths a failed provisioning step reported as left on disk, if any."""
    return error.leftovers if isinstance(error, ServerProvisioningError) else ()


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
