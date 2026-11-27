"""Every backend error has a translated message (M4-BE-01).

The table below lists every exception class MCServer's domain, application,
infrastructure and bootstrap code defines. A class either maps to a specific
message key, or is listed in ``INTERNAL`` with the reason it never reaches the
user. A new exception class makes ``test_every_backend_error_is_classified``
fail until it is added to one of the two, so no error can silently fall back
to "Something went wrong".
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import re
from pathlib import Path

import pytest

import mcserver
from mcserver.application.errors import ProcessGuardUnavailable, ServerProvisioningError, ServerStartFailed
from mcserver.presentation.errors import UserMessage, describe_error, error_tone, render_message
from mcserver.presentation.i18n import en, messages_for, uk

EXPECTED: dict[str, str] = {
    # application/backups.py
    "mcserver.application.backups.BackupFailed": "errors.backup_failed",
    "mcserver.application.backups.BackupNotFound": "errors.backup_not_found",
    "mcserver.application.backups.BackupNotPossible": "errors.backup_not_possible",
    # application/backup_schedule.py
    "mcserver.application.backup_schedule.InvalidBackupSchedule": "errors.invalid_schedule",
    # application/errors.py
    "mcserver.application.errors.ActiveServerAlreadyExists": "errors.another_server_running",
    "mcserver.application.errors.EulaNotAccepted": "errors.eula_not_accepted",
    "mcserver.application.errors.InvalidJavaExecutable": "errors.invalid_java",
    "mcserver.application.errors.InvalidServerCommand": "errors.invalid_command",
    "mcserver.application.errors.InvalidSourceJar": "errors.invalid_source_jar",
    "mcserver.application.errors.JavaNotFound": "errors.java_not_found",
    "mcserver.application.errors.JavaVersionTooOld": "errors.java_too_old",
    "mcserver.application.errors.LegacyConfigurationUnavailable": "errors.legacy_unavailable",
    "mcserver.application.errors.ProvisioningRollbackFailed": "errors.provisioning_rollback_failed",
    "mcserver.application.errors.ServerCommandFailed": "errors.command_failed",
    "mcserver.application.errors.ServerConfigurationAlreadyExists": "errors.server_id_taken",
    "mcserver.application.errors.ServerConfigurationNotFound": "errors.server_not_found",
    "mcserver.application.errors.ServerConfigurationStorageError": "errors.storage_failed",
    "mcserver.application.errors.ServerCreationRollbackFailed": "errors.creation_rollback_failed",
    "mcserver.application.errors.ServerDirectoryAlreadyExists": "errors.directory_exists",
    "mcserver.application.errors.ServerDirectoryInUse": "errors.directory_in_use",
    "mcserver.application.errors.ServerFilesRemovalFailed": "errors.files_removal_failed",
    "mcserver.application.errors.ServerFilesystemError": "errors.provisioning_failed",
    "mcserver.application.errors.ServerIsRunning": "errors.server_is_running",
    "mcserver.application.errors.ServerJarAlreadyExists": "errors.jar_exists",
    "mcserver.application.errors.ServerNotRunning": "errors.server_not_running",
    "mcserver.application.errors.ServerPortInUse": "errors.server_port_in_use",
    "mcserver.application.errors.ServerProvisioningError": "errors.provisioning_failed",
    "mcserver.application.errors.ServerStartFailed": "errors.start_failed",
    "mcserver.application.errors.ServerStopFailed": "errors.stop_failed",
    "mcserver.application.errors.ServerStopTimedOut": "errors.stop_timed_out",
    "mcserver.application.errors.ServerWorldInUse": "errors.world_in_use",
    "mcserver.application.errors.UnsafeServerPath": "errors.provisioning_failed",
    # application/progress.py and the catalog
    "mcserver.application.progress.OperationCancelled": "progress.cancelled",
    "mcserver.application.server_catalog.CatalogUnavailable": "errors.catalog_unavailable",
    "mcserver.application.server_catalog.DownloadCancelled": "progress.cancelled",
    "mcserver.application.server_catalog.DownloadFailed": "errors.download_failed",
    # application/settings.py
    "mcserver.application.settings.InvalidSettings": "errors.invalid_settings",
    # application/worlds.py
    "mcserver.application.worlds.InvalidWorldName": "errors.invalid_world_name",
    "mcserver.application.worlds.InvalidWorldSource": "errors.invalid_world_source",
    "mcserver.application.worlds.WorldAlreadyExists": "errors.world_exists",
    "mcserver.application.worlds.WorldIsActive": "errors.world_is_active",
    "mcserver.application.worlds.WorldNotFound": "errors.world_not_found",
    # domain
    "mcserver.domain.errors.InvalidServerConfiguration": "errors.invalid_configuration",
    "mcserver.domain.server_properties.InvalidServerProperties": "errors.invalid_properties",
    # infrastructure: storage errors surface as "could not save the server list"
    "mcserver.infrastructure.server_configuration_store.CorruptServerConfigurationFile": "errors.storage_failed",
    "mcserver.infrastructure.server_configuration_store.ServerConfigurationFileError": "errors.storage_failed",
    "mcserver.infrastructure.server_configuration_store.ServerConfigurationWriteFailed": "errors.storage_failed",
    "mcserver.infrastructure.server_configuration_store.UnsupportedServerConfigurationFormat": "errors.storage_failed",
}

INTERNAL: dict[str, str] = {
    "mcserver.application.backups.BackupError": "abstract base; only its subclasses are raised",
    "mcserver.application.server_catalog.CatalogError": "abstract base; only its subclasses are raised",
    "mcserver.application.worlds.WorldError": "abstract base; only its subclasses are raised",
    "mcserver.application.errors.ProcessGuardUnavailable": "raised inside the runner; reaches the GUI only as the "
    "cause of ServerStartFailed (errors.process_guard)",
    "mcserver.application.errors.LegacyServerEntryInvalid": "caught by the 0.9.1 import and listed in its result",
    "mcserver.domain.errors.InvalidStateTransition": "a programming-error guard; the generic message with details "
    "is the right answer",
    "mcserver.infrastructure.process_runner.InvalidProcessConfiguration": "wrapped in ServerStartFailed by the "
    "coordinator",
    "mcserver.infrastructure.process_runner.ProcessAlreadyRunning": "wrapped in ServerStartFailed by the coordinator",
    "mcserver.infrastructure.process_runner.ProcessStartError": "wrapped in ServerStartFailed by the coordinator",
    "mcserver.infrastructure.server_configuration.ServerConfigurationError": "legacy 0.9.1 reader; caught by the "
    "legacy import",
}

GENERIC = "errors.unexpected"
PLACEHOLDER = re.compile(r"\{[a-z_]+(?::[^}]*)?\}")


def backend_exception_classes() -> dict[str, type[BaseException]]:
    """Return every exception class defined outside ``mcserver.presentation``."""
    found: dict[str, type[BaseException]] = {}
    for info in pkgutil.walk_packages(mcserver.__path__, "mcserver."):
        if info.name.startswith("mcserver.presentation") or info.name.endswith("__main__"):
            continue
        module = importlib.import_module(info.name)
        for name, value in vars(module).items():
            if inspect.isclass(value) and issubclass(value, BaseException) and value.__module__ == info.name:
                found[f"{info.name}.{name}"] = value
    return found


CLASSES = backend_exception_classes()


def _sample(parameter: inspect.Parameter) -> object:
    annotation = str(parameter.annotation)
    if "tuple" in annotation:
        return ("servers/survival/partial.tmp",)
    if "Mapping" in annotation:
        return {"max-players": "not a number"}
    if "Path" in annotation:
        return Path("servers.json")
    if "float" in annotation:
        return 30.0
    if "int" in annotation:
        return 21
    if "ServerProvisioningError" in annotation:
        return ServerProvisioningError("copy failed", ("servers/survival/world",))
    if "Exception" in annotation:
        return OSError("disk full")
    return f"sample-{parameter.name}"


def instance(cls: type[BaseException]) -> BaseException:
    """Build ``cls`` with plausible values for its required constructor arguments."""
    parameters = [
        parameter
        for parameter in list(inspect.signature(cls.__init__).parameters.values())[1:]
        if parameter.kind is parameter.POSITIONAL_OR_KEYWORD and parameter.default is parameter.empty
    ]
    if not parameters:
        return cls("sample message")
    return cls(*[_sample(parameter) for parameter in parameters])


def test_every_backend_error_is_classified() -> None:
    discovered = set(CLASSES)
    classified = set(EXPECTED) | set(INTERNAL)
    assert not set(EXPECTED) & set(INTERNAL)
    assert discovered - classified == set(), "add these to EXPECTED (with a message) or INTERNAL (with a reason)"
    assert classified - discovered == set(), "these classes no longer exist; remove them from the table"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_error_gets_its_own_message(name: str) -> None:
    assert describe_error(instance(CLASSES[name])).key == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(EXPECTED))
@pytest.mark.parametrize("language", ["en", "uk"])
def test_each_message_renders_completely_in_every_language(
    name: str, language: str, caplog: pytest.LogCaptureFixture
) -> None:
    messages = messages_for(language)
    message = describe_error(instance(CLASSES[name]))
    catalog = en.MESSAGES if language == "en" else uk.MESSAGES
    assert message.key in catalog, f"{message.key} is missing in {language}.json"

    with caplog.at_level(logging.WARNING, logger="mcserver.presentation.i18n.catalog"):
        text = render_message(messages, message)

    assert caplog.records == [], f"{message.key} could not be filled in: {caplog.text}"
    assert text and text != message.key
    assert not PLACEHOLDER.search(text), f"unfilled placeholder in {text!r}"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_errors_carry_technical_details_and_the_right_tone(name: str) -> None:
    error = instance(CLASSES[name])
    message = describe_error(error)
    if message.key == "progress.cancelled":
        assert error_tone(error) == "notice"
        return
    assert error_tone(error) == "error"
    assert type(error).__name__ in message.details


@pytest.mark.parametrize("name", sorted(INTERNAL))
def test_internal_errors_still_get_the_generic_message_with_details(name: str) -> None:
    error = instance(CLASSES[name])
    message = describe_error(error)
    assert message.key == GENERIC
    assert type(error).__name__ in message.details


def test_a_wrapped_cause_chooses_the_message() -> None:
    start = ServerStartFailed("survival")
    start.__cause__ = ProcessGuardUnavailable("job object refused")
    message = describe_error(start)
    assert message.key == "errors.process_guard"
    assert "ProcessGuardUnavailable: job object refused" in message.details


def test_errors_from_outside_mcserver_fall_back_safely() -> None:
    message = describe_error(PermissionError(13, "Access is denied", "C:/servers"))
    assert message.key == GENERIC
    assert message.details.startswith("PermissionError")
    assert render_message(messages_for("uk"), message) == messages_for("uk").text(GENERIC)


def test_every_error_text_in_the_catalog_is_used() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path(mcserver.__file__).parent.joinpath("presentation").rglob("*.py")
    )
    unused = [key for key in en.MESSAGES if key.startswith("errors.") and f'"{key}"' not in source]
    assert unused == [], "remove these texts or map an error to them"


def test_user_message_keys_used_by_the_mapping_exist_in_both_languages() -> None:
    keys = {describe_error(instance(cls)).key for cls in CLASSES.values()} | {"errors.process_guard", GENERIC}
    for key in keys:
        assert key in en.MESSAGES and key in uk.MESSAGES, key
    assert isinstance(describe_error(OSError()), UserMessage)
