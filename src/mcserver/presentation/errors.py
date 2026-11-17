"""Turn backend exceptions into user-facing messages; independent of Qt."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from mcserver.application.errors import (
    ActiveServerAlreadyExists,
    EulaNotAccepted,
    InvalidJavaExecutable,
    InvalidServerCommand,
    InvalidSourceJar,
    JavaNotFound,
    JavaVersionTooOld,
    ProcessGuardUnavailable,
    ProvisioningRollbackFailed,
    ServerCommandFailed,
    ServerConfigurationAlreadyExists,
    ServerConfigurationStorageError,
    ServerCreationRollbackFailed,
    ServerDirectoryAlreadyExists,
    ServerDirectoryInUse,
    ServerJarAlreadyExists,
    ServerNotRunning,
    ServerProvisioningError,
    ServerStartFailed,
    ServerStopFailed,
    ServerStopTimedOut,
    ServerWorldInUse,
)
from mcserver.application.server_coordinator import FailureKind, ServerFailure
from mcserver.domain.diagnostics import FailureHint
from mcserver.domain.errors import InvalidServerConfiguration
from mcserver.presentation.i18n.catalog import Messages


@dataclass(frozen=True, slots=True)
class UserMessage:
    """A message key with parameters for the catalog, plus untranslated technical details."""

    key: str
    params: Mapping[str, object] = field(default_factory=dict)
    details: str = ""


def render_message(messages: Messages, message: UserMessage) -> str:
    """Render ``message``; a parameter named ``<name>_key`` is translated and passed as ``<name>``."""
    params: dict[str, object] = {}
    nested: dict[str, object] = {}
    for name, value in message.params.items():
        if name.endswith("_key") and isinstance(value, str):
            nested[name[: -len("_key")]] = value
        else:
            params[name] = value
    for name, key in nested.items():
        params[name] = messages.text(str(key), **params)
    return messages.text(message.key, **params)


def describe_error(error: BaseException) -> UserMessage:
    """Map an exception to a message; unknown errors get a generic message with details."""
    details = technical_details(error)
    if isinstance(error, ActiveServerAlreadyExists):
        return UserMessage("errors.another_server_running", {"server_id": error.active_server_id}, details)
    runtime = _describe_runtime_error(error, details)
    if runtime is not None:
        return runtime
    creation = _describe_creation_error(error, details)
    if creation is not None:
        return creation
    return UserMessage("errors.unexpected", {}, details)


def _describe_runtime_error(error: BaseException, details: str) -> UserMessage | None:
    """Messages for starting, stopping and commanding a server."""
    if isinstance(error, ServerStartFailed):
        if isinstance(error.__cause__, ProcessGuardUnavailable):
            return UserMessage("errors.process_guard", {"server_id": error.server_id}, details)
        return UserMessage("errors.start_failed", {"server_id": error.server_id}, details)
    if isinstance(error, ServerStopTimedOut):
        return UserMessage(
            "errors.stop_timed_out", {"server_id": error.server_id, "timeout": f"{error.timeout:g}"}, details
        )
    if isinstance(error, ServerStopFailed):
        return UserMessage("errors.stop_failed", {"server_id": error.server_id}, details)
    if isinstance(error, EulaNotAccepted):
        return UserMessage("errors.eula_not_accepted", {"server_id": error.server_id}, details)
    if isinstance(error, JavaVersionTooOld):
        return UserMessage(
            "errors.java_too_old",
            {"server_id": error.server_id, "required": error.required_major, "found": error.found_major},
            details,
        )
    if isinstance(error, JavaNotFound):
        return UserMessage("errors.java_not_found", {}, details)
    if isinstance(error, InvalidJavaExecutable):
        return UserMessage("errors.invalid_java", {"executable": error.executable}, details)
    if isinstance(error, ServerWorldInUse):
        return UserMessage("errors.world_in_use", {"server_id": error.server_id, "world": error.world}, details)
    if isinstance(error, ServerNotRunning):
        return UserMessage("errors.server_not_running", {"server_id": error.server_id}, details)
    if isinstance(error, InvalidServerCommand):
        return UserMessage("errors.invalid_command", {}, details)
    if isinstance(error, ServerCommandFailed):
        return UserMessage("errors.command_failed", {"server_id": error.server_id}, details)
    return None


FAILURE_KEYS = {
    FailureKind.START_TIMEOUT: "dashboard.failure.start_timeout",
    FailureKind.UNEXPECTED_EXIT: "dashboard.failure.unexpected_exit",
}
HINT_KEYS = {hint: f"hint.{hint.value}" for hint in FailureHint}


def describe_failure(failure: ServerFailure) -> UserMessage:
    """Describe a failed run: what happened, the likely cause, and the evidence as details."""
    lines: list[str] = []
    if failure.exit_code is not None:
        lines.append(f"exit code: {failure.exit_code}")
    lines.extend(failure.output_tail)
    return UserMessage(
        FAILURE_KEYS[failure.kind],
        {
            "server_id": failure.server_id,
            "exit_code": "-" if failure.exit_code is None else failure.exit_code,
            "hint_key": HINT_KEYS[failure.hint],
        },
        "\n".join(lines),
    )


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
