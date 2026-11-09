"""Tests for the create-server controller, using the real ServerCreation over in-memory fakes."""

from dataclasses import replace
from threading import Event

import pytest
from fakes import InMemoryRepository, MemoryFilesystem, creation_for, management_for
from pytestqt.qtbot import QtBot

from mcserver.application.errors import ServerFilesystemError
from mcserver.domain.server_configuration import MAX_MEMORY_MB, MIN_MEMORY_MB, ServerConfiguration
from mcserver.presentation.controllers.server_creation import (
    DEFAULT_MEMORY_MB,
    CreationForm,
    CreationState,
    ServerCreationController,
)
from mcserver.presentation.errors import describe_error
from mcserver.presentation.i18n import en
from mcserver.presentation.workers import BackgroundRunner

SOURCE = r"C:\Downloads\paper-1.21.4.jar"
LOBBY = ServerConfiguration("lobby", "lobby", "velocity.jar", 1024)
VALID = CreationForm(server_id="survival", directory="survival", source_jar=SOURCE, memory_mb=4096)


class Harness:
    def __init__(self, *existing: ServerConfiguration, directories: tuple[str, ...] = ()) -> None:
        self.repository = InMemoryRepository(*existing)
        self.filesystem = MemoryFilesystem(*directories)
        self.controller = ServerCreationController(
            creation_for(self.repository, self.filesystem), management_for(self.repository), BackgroundRunner()
        )
        self.states: list[CreationState] = []
        self.created: list[ServerConfiguration] = []
        self.controller.state_changed.connect(self.states.append)
        self.controller.created.connect(self.created.append)
        self.controller.begin()


@pytest.fixture
def harness(qtbot: QtBot) -> Harness:
    return Harness(LOBBY)


# --- validation ---------------------------------------------------------------------------


def test_jar_file_is_derived_from_selected_source() -> None:
    assert VALID.jar_file == "paper-1.21.4.jar"
    assert CreationForm().jar_file == ""
    assert CreationForm().memory_mb == DEFAULT_MEMORY_MB == 4096


def test_valid_form_has_no_errors(harness: Harness) -> None:
    assert harness.controller.validate(VALID).ok


@pytest.mark.parametrize(
    ("changes", "field", "key"),
    [
        ({"server_id": ""}, "server_id", "create.error.server_id_required"),
        ({"server_id": "   "}, "server_id", "create.error.server_id_required"),
        ({"server_id": " survival"}, "server_id", "create.error.server_id_invalid"),
        ({"server_id": "a/b"}, "server_id", "create.error.server_id_invalid"),
        ({"server_id": "CON"}, "server_id", "create.error.server_id_invalid"),
        ({"server_id": "lobby"}, "server_id", "create.error.server_id_taken"),
        ({"directory": ""}, "directory", "create.error.directory_required"),
        ({"directory": "..\\outside"}, "directory", "create.error.directory_invalid"),
        ({"directory": "C:\\abs"}, "directory", "create.error.directory_invalid"),
        ({"directory": "LOBBY"}, "directory", "create.error.directory_taken"),
        ({"source_jar": ""}, "source_jar", "create.error.jar_required"),
        ({"source_jar": r"C:\Downloads\server.zip"}, "source_jar", "create.error.jar_invalid"),
        ({"memory_mb": MIN_MEMORY_MB - 1}, "memory_mb", "create.error.memory_range"),
        ({"memory_mb": MAX_MEMORY_MB + 1}, "memory_mb", "create.error.memory_range"),
    ],
)
def test_invalid_fields_are_reported(harness: Harness, changes: dict[str, object], field: str, key: str) -> None:
    form = replace(VALID, **changes)  # type: ignore[arg-type]

    validation = harness.controller.validate(form)

    assert validation.errors.get(field) == key
    assert key in en.MESSAGES


def test_directory_taken_reports_owner(harness: Harness) -> None:
    assert harness.controller.taken_directory_owner("Lobby") == "lobby"
    assert harness.controller.taken_directory_owner("survival") is None


def test_invalid_form_is_not_submitted(harness: Harness) -> None:
    assert harness.controller.submit(CreationForm(server_id="lobby", directory="x", source_jar=SOURCE)) is False
    assert harness.filesystem.calls == []
    assert not harness.controller.busy


# --- submission ---------------------------------------------------------------------------


def test_successful_creation_calls_backend_with_derived_arguments(qtbot: QtBot, harness: Harness) -> None:
    assert harness.controller.submit(VALID) is True
    assert harness.controller.busy

    qtbot.waitUntil(lambda: harness.created != [])
    created = harness.created[0]
    assert created == ServerConfiguration("survival", "survival", "paper-1.21.4.jar", 4096)
    assert harness.repository.items["survival"] == created
    assert harness.filesystem.tree["survival"] == {"paper-1.21.4.jar": SOURCE}
    assert harness.states[-1] == CreationState()
    assert not harness.controller.busy


def test_repeated_submission_is_refused_while_busy(qtbot: QtBot, harness: Harness) -> None:
    harness.filesystem.install_gate = Event()

    assert harness.controller.submit(VALID) is True
    assert harness.controller.submit(VALID) is False
    harness.filesystem.install_gate.set()

    qtbot.waitUntil(lambda: harness.created != [])
    assert [call for call in harness.filesystem.calls if call.startswith("create:")] == ["create:survival"]


def test_duplicate_added_meanwhile_is_rejected_at_submit(qtbot: QtBot, harness: Harness) -> None:
    harness.repository.items["survival"] = ServerConfiguration("survival", "other", "x.jar", 1024)

    assert harness.controller.submit(VALID) is False  # re-read on submit
    assert harness.controller.validate(VALID).errors["server_id"] == "create.error.server_id_taken"


def test_existing_folder_on_disk_fails_in_backend_and_leaves_nothing(qtbot: QtBot) -> None:
    harness = Harness(directories=("survival",))

    harness.controller.submit(VALID)

    qtbot.waitUntil(lambda: harness.states[-1].error is not None)
    error = harness.states[-1].error
    assert error is not None and error.key == "errors.directory_exists"
    assert "survival" not in harness.repository.items  # rolled back by the backend
    assert harness.created == []
    assert not harness.controller.busy


def test_copy_failure_is_reported_with_details(qtbot: QtBot, harness: Harness) -> None:
    harness.filesystem.install_error = ServerFilesystemError("disk full")

    harness.controller.submit(VALID)

    qtbot.waitUntil(lambda: harness.states[-1].error is not None)
    error = harness.states[-1].error
    assert error is not None and error.key == "errors.provisioning_failed"
    assert "ServerFilesystemError: disk full" in error.details
    assert "survival" not in harness.repository.items
    assert "survival" not in harness.filesystem.tree


def test_missing_source_file_is_reported(qtbot: QtBot, harness: Harness) -> None:
    harness.filesystem.missing_sources.add(SOURCE)

    harness.controller.submit(VALID)

    qtbot.waitUntil(lambda: harness.states[-1].error is not None)
    error = harness.states[-1].error
    assert error is not None and error.key == "errors.invalid_source_jar"
    assert error.params == {"reason": "the file does not exist"}


def test_creation_rollback_failure_names_leftovers_and_both_errors(qtbot: QtBot, harness: Harness) -> None:
    harness.filesystem.install_error = ServerFilesystemError(
        "copy failed; partial file kept", leftovers=("survival/paper-1.21.4.jar",)
    )
    harness.repository.broken_remove = True

    harness.controller.submit(VALID)

    qtbot.waitUntil(lambda: harness.states[-1].error is not None)
    error = harness.states[-1].error
    assert error is not None and error.key == "errors.creation_rollback_failed"
    assert error.params["server_id"] == "survival"
    assert "survival/paper-1.21.4.jar" in str(error.params["leftovers"])
    assert "ServerCreationRollbackFailed" in error.details
    assert "disk full" in error.details  # the rollback cause is kept


def test_new_attempt_clears_previous_error(qtbot: QtBot, harness: Harness) -> None:
    harness.filesystem.install_error = ServerFilesystemError("disk full")
    harness.controller.submit(VALID)
    qtbot.waitUntil(lambda: harness.states[-1].error is not None)
    harness.filesystem.install_error = None

    harness.controller.submit(VALID)

    assert harness.states[-1] == CreationState(busy=True)
    qtbot.waitUntil(lambda: harness.created != [])


def test_unexpected_error_still_produces_a_message() -> None:
    message = describe_error(RuntimeError("worker exploded"))

    assert message.key == "errors.unexpected"
    assert "worker exploded" in message.details


def test_all_creation_error_keys_exist() -> None:
    keys = {
        "errors.server_id_taken",
        "errors.directory_in_use",
        "errors.directory_exists",
        "errors.jar_exists",
        "errors.invalid_source_jar",
        "errors.invalid_configuration",
        "errors.provisioning_failed",
        "errors.storage_failed",
        "errors.provisioning_rollback_failed",
        "errors.creation_rollback_failed",
    }

    assert sorted(keys - set(en.MESSAGES)) == []
