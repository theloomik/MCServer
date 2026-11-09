"""Offscreen Qt tests for the create-server dialog and its integration with the main window."""

from pathlib import Path
from threading import Event

from fakes import InMemoryRepository, MemoryFilesystem, creation_for, management_for, services_for
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from mcserver.application.errors import ServerFilesystemError
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.presentation.controllers.server_creation import ServerCreationController
from mcserver.presentation.dialogs.create_server_dialog import CreateServerDialog
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.main_window import MainWindow
from mcserver.presentation.workers import BackgroundRunner

SOURCE = r"C:\Downloads\paper-1.21.4.jar"
LOBBY = ServerConfiguration("lobby", "lobby", "velocity.jar", 1024)
MESSAGES = messages_for()


class DialogSetup:
    def __init__(self, qtbot: QtBot, *, picks: list[str | None] | None = None) -> None:
        self.repository = InMemoryRepository(LOBBY)
        self.filesystem = MemoryFilesystem()
        self.controller = ServerCreationController(
            creation_for(self.repository, self.filesystem), management_for(self.repository), BackgroundRunner()
        )
        self.picks = list(picks if picks is not None else [SOURCE])
        self.dialog = CreateServerDialog(self.controller, MESSAGES, pick_jar=lambda _parent: self.picks.pop(0))
        qtbot.addWidget(self.dialog)
        self.dialog.show()

    def fill(self, qtbot: QtBot, server_id: str = "survival") -> None:
        qtbot.keyClicks(self.dialog.server_id_edit, server_id)
        qtbot.mouseClick(self.dialog.browse_button, Qt.MouseButton.LeftButton)


def test_dialog_renders_fields_with_catalog_texts_and_defaults(qtbot: QtBot) -> None:
    setup = DialogSetup(qtbot)
    dialog = setup.dialog

    assert dialog.windowTitle() == MESSAGES.text("create.title")
    assert dialog.memory_spin.value() == 4096
    assert dialog.jar_edit.isReadOnly()
    assert dialog.jar_edit.placeholderText() == MESSAGES.text("create.jar.placeholder")
    assert dialog.create_button.text() == MESSAGES.text("create.submit")
    assert not dialog.create_button.isEnabled()
    assert all(label.isHidden() for label in dialog.field_errors.values())  # no errors before typing


def test_directory_follows_server_id_until_edited(qtbot: QtBot) -> None:
    dialog = DialogSetup(qtbot).dialog

    qtbot.keyClicks(dialog.server_id_edit, "survival")
    assert dialog.directory_edit.text() == "survival"

    dialog.directory_edit.clear()
    qtbot.keyClicks(dialog.directory_edit, "smp-files")
    qtbot.keyClicks(dialog.server_id_edit, "-2")

    assert dialog.directory_edit.text() == "smp-files"


def test_jar_selection_shows_file_name_and_full_path_on_hover(qtbot: QtBot) -> None:
    setup = DialogSetup(qtbot)

    setup.fill(qtbot)

    assert setup.dialog.jar_edit.text() == "paper-1.21.4.jar"
    assert setup.dialog.jar_edit.toolTip() == SOURCE
    assert setup.dialog.create_button.isEnabled()


def test_cancelled_file_dialog_keeps_previous_choice(qtbot: QtBot) -> None:
    setup = DialogSetup(qtbot, picks=[SOURCE, None])
    setup.fill(qtbot)

    qtbot.mouseClick(setup.dialog.browse_button, Qt.MouseButton.LeftButton)

    assert setup.dialog.form().source_jar == SOURCE


def test_validation_messages_appear_next_to_fields(qtbot: QtBot) -> None:
    setup = DialogSetup(qtbot)
    dialog = setup.dialog

    qtbot.keyClicks(dialog.server_id_edit, "lobby")

    error = dialog.field_errors["server_id"]
    assert not error.isHidden()
    assert error.text() == MESSAGES.text("create.error.server_id_taken")
    directory_error = dialog.field_errors["directory"]
    assert directory_error.text() == MESSAGES.text("create.error.directory_taken", server_id="lobby")
    assert not dialog.create_button.isEnabled()


def test_submitting_incomplete_form_reveals_all_required_errors(qtbot: QtBot) -> None:
    dialog = DialogSetup(qtbot).dialog
    dialog.create_button.setEnabled(True)  # simulate a stray click path

    dialog.create_button.click()

    assert dialog.field_errors["server_id"].text() == MESSAGES.text("create.error.server_id_required")
    assert dialog.field_errors["source_jar"].text() == MESSAGES.text("create.error.jar_required")
    assert dialog.isVisible()


def test_controls_are_disabled_and_dialog_cannot_close_while_creating(qtbot: QtBot) -> None:
    setup = DialogSetup(qtbot)
    setup.filesystem.install_gate = Event()
    setup.fill(qtbot)
    dialog = setup.dialog

    qtbot.mouseClick(dialog.create_button, Qt.MouseButton.LeftButton)

    assert not dialog.create_button.isEnabled() and not dialog.cancel_button.isEnabled()
    assert not dialog.server_id_edit.isEnabled() and not dialog.browse_button.isEnabled()
    assert dialog.create_button.text() == MESSAGES.text("create.submitting")
    assert dialog.progress.isVisible()
    dialog.reject()
    dialog.close()
    assert dialog.isVisible()

    setup.filesystem.install_gate.set()
    qtbot.waitUntil(lambda: not dialog.isVisible())
    assert dialog.created_server_id == "survival"
    assert dialog.result() == CreateServerDialog.DialogCode.Accepted


def test_failure_keeps_dialog_open_with_error_and_details(qtbot: QtBot) -> None:
    setup = DialogSetup(qtbot)
    setup.filesystem.install_error = ServerFilesystemError("disk full")
    setup.fill(qtbot)
    dialog = setup.dialog

    qtbot.mouseClick(dialog.create_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: dialog.error_banner.isVisible())
    assert dialog.error_banner.text() == MESSAGES.text("errors.provisioning_failed")
    assert "ServerFilesystemError: disk full" in dialog.details_label.text()
    assert dialog.isVisible()
    assert dialog.create_button.isEnabled() and dialog.cancel_button.isEnabled()
    assert not dialog.progress.isVisible()


def test_cancel_closes_without_creating(qtbot: QtBot) -> None:
    setup = DialogSetup(qtbot)
    setup.fill(qtbot)

    qtbot.mouseClick(setup.dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert not setup.dialog.isVisible()
    assert setup.dialog.result() == CreateServerDialog.DialogCode.Rejected
    assert setup.filesystem.calls == []
    assert "survival" not in setup.repository.items


# --- main window integration ------------------------------------------------------------------


class WindowSetup:
    def __init__(self, qtbot: QtBot, root: Path, *, java: bool = True) -> None:
        self.repository = InMemoryRepository(LOBBY)
        self.filesystem = MemoryFilesystem()
        services = services_for(self.repository, root=root, java=java, filesystem=self.filesystem)
        self.window = MainWindow(
            services,
            MESSAGES,
            confirm_exit=lambda _server_id: True,
            create_dialog=lambda controller, messages, parent: CreateServerDialog(
                controller, messages, parent, pick_jar=lambda _parent: SOURCE
            ),
        )
        qtbot.addWidget(self.window)
        self.window.show()


def test_sidebar_button_opens_single_dialog(qtbot: QtBot, tmp_path: Path) -> None:
    setup = WindowSetup(qtbot, tmp_path)
    button = setup.window.server_list_view.create_button
    assert button.text() == MESSAGES.text("server_list.create")

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    first = setup.window.create_dialog
    setup.window.new_server_action.trigger()

    assert first is not None and first.isVisible()
    assert setup.window.create_dialog is first


def test_successful_creation_selects_new_stopped_server_with_confirmation(qtbot: QtBot, tmp_path: Path) -> None:
    setup = WindowSetup(qtbot, tmp_path)
    setup.window.open_create_dialog()
    dialog = setup.window.create_dialog
    assert dialog is not None
    qtbot.keyClicks(dialog.server_id_edit, "survival")
    qtbot.mouseClick(dialog.browse_button, Qt.MouseButton.LeftButton)

    qtbot.mouseClick(dialog.create_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: setup.window.create_dialog is None)
    window = setup.window
    assert window.server_list_view.server_ids() == ["lobby", "survival"]
    assert window.server_list_view.list_widget.currentRow() == 1
    dashboard = window.dashboard_view
    assert dashboard.title_label.text() == "survival"
    assert dashboard.status_pill.property("status") == "stopped"
    assert dashboard.banner.isVisible() and dashboard.banner.property("tone") == "success"
    assert dashboard.banner.text() == MESSAGES.text("dashboard.success.created", server_id="survival")
    assert window.statusBar().currentMessage() == MESSAGES.text("create.done", server_id="survival")
    assert setup.filesystem.tree["survival"] == {"paper-1.21.4.jar": SOURCE}


def test_creation_works_without_java(qtbot: QtBot, tmp_path: Path) -> None:
    setup = WindowSetup(qtbot, tmp_path, java=False)
    assert setup.window.server_list_view.create_button.isEnabled()
    setup.window.open_create_dialog()
    dialog = setup.window.create_dialog
    assert dialog is not None
    qtbot.keyClicks(dialog.server_id_edit, "survival")
    qtbot.mouseClick(dialog.browse_button, Qt.MouseButton.LeftButton)

    qtbot.mouseClick(dialog.create_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: "survival" in setup.repository.items)
    qtbot.waitUntil(lambda: setup.window.dashboard_view.title_label.text() == "survival")
    assert not setup.window.dashboard_view.start_button.isEnabled()


def test_window_refuses_to_close_while_creating(qtbot: QtBot, tmp_path: Path) -> None:
    setup = WindowSetup(qtbot, tmp_path)
    setup.filesystem.install_gate = Event()
    setup.window.open_create_dialog()
    dialog = setup.window.create_dialog
    assert dialog is not None
    qtbot.keyClicks(dialog.server_id_edit, "survival")
    qtbot.mouseClick(dialog.browse_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(dialog.create_button, Qt.MouseButton.LeftButton)

    setup.window.close()

    assert setup.window.isVisible()
    assert setup.window.statusBar().currentMessage() == MESSAGES.text("exit.wait_for_operation")
    setup.filesystem.install_gate.set()
    qtbot.waitUntil(lambda: setup.window.create_dialog is None)
