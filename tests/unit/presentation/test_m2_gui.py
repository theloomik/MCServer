"""Offscreen Qt tests for M2: edit, delete, folder import, settings and the legacy import offer."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import FakeRunnerFactory, InMemoryRepository, MemoryFilesystem, creation_for
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from mcserver.application.errors import InvalidJavaExecutable
from mcserver.application.java_setup import JavaSetup
from mcserver.application.ports import JavaInstallation, RemovedServerFiles
from mcserver.application.server_adoption import ServerAdoption
from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_management import LegacyImportResult, ServerManagement
from mcserver.application.server_output import ServerOutputBuffer
from mcserver.application.settings import ApplicationSettings, SettingsService
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.server_folders import LocalServerFolderAdoption
from mcserver.infrastructure.settings_store import JsonApplicationSettingsStore
from mcserver.presentation.dialogs.edit_server_dialog import join_arguments, split_arguments
from mcserver.presentation.dialogs.settings_dialog import SettingsDialog
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.main_window import MainWindow
from mcserver.presentation.services import PresentationServices
from tests.runtime_fakes import ManualScheduler

MESSAGES = messages_for()
SURVIVAL = ServerConfiguration("survival", "survival", "paper.jar", 4096)


class Legacy:
    def __init__(self, *configurations: ServerConfiguration) -> None:
        self.items = {configuration.server_id: configuration for configuration in configurations}

    def list_server_ids(self) -> tuple[str, ...]:
        return tuple(self.items)

    def read_server(self, server_id: str) -> ServerConfiguration:
        return self.items[server_id]


class Remover:
    def __init__(self) -> None:
        self.removed: list[str] = []

    def remove_server_files(self, directory: str) -> RemovedServerFiles:
        self.removed.append(directory)
        return RemovedServerFiles("recycle_bin", directory)


class Java:
    configured_executable: str | None = None

    def find(self, minimum_major: int | None = None) -> JavaInstallation:
        return JavaInstallation("C:/jdk/bin/java.exe", 21, "path")

    def inspect(self, executable: str) -> JavaInstallation:
        if "broken" in executable:
            raise InvalidJavaExecutable(executable)
        return JavaInstallation(executable, 21, "server")

    def configure(self, executable: str | None) -> JavaInstallation | None:
        if executable is not None and "broken" in executable:
            raise InvalidJavaExecutable(executable)
        self.configured_executable = executable
        return None


class Setup:
    def __init__(
        self,
        qtbot: QtBot,
        root: Path,
        *configurations: ServerConfiguration,
        legacy: Legacy | None = None,
        offer_answer: bool = True,
        delete_answer: bool | None = False,
    ) -> None:
        self.repository = InMemoryRepository(*configurations)
        self.factory = FakeRunnerFactory()
        self.coordinator = ServerCoordinator(self.factory, scheduler=ManualScheduler())
        self.remover = Remover()
        self.management = ServerManagement(
            self.repository,
            legacy or Legacy(),
            active_server=lambda: self.coordinator.active_server_id,
            files_remover=self.remover,
        )
        self.java = Java()
        self.settings = SettingsService(JsonApplicationSettingsStore(root), self.java)  # type: ignore[arg-type]
        self.offers: list[int] = []
        self.results: list[LegacyImportResult] = []
        self.delete_questions: list[str] = []
        services = PresentationServices(
            servers_root=root,
            management=self.management,
            server_creation=creation_for(self.repository, MemoryFilesystem()),
            coordinator=self.coordinator,
            output=ServerOutputBuffer(),
            java_problem=None,
            closer=lambda: None,
            java=JavaSetup(self.java),  # type: ignore[arg-type]
            settings=self.settings,
            adoption=ServerAdoption(self.management, LocalServerFolderAdoption(root)),
        )

        def ask_delete(configuration: ServerConfiguration, _folder: Path) -> bool | None:
            self.delete_questions.append(configuration.server_id)
            return delete_answer

        self.window = MainWindow(
            services,
            MESSAGES,
            confirm_exit=lambda _server_id: True,
            ask_delete=ask_delete,
            offer_legacy_import=lambda count: self.offers.append(count) or offer_answer,
            notify_legacy_result=self.results.append,
            notify_unclean=lambda _incident: None,
        )
        qtbot.addWidget(self.window)
        self.window.show()
        self.qtbot = qtbot

    def select(self, row: int = 0) -> None:
        self.window.server_list_view.list_widget.setCurrentRow(row)

    @property
    def dashboard(self):  # type: ignore[no-untyped-def]
        return self.window.dashboard_view


# --- list and dashboard show the display name (M2-GUI-06) ------------------------------------


def test_display_name_is_shown_in_list_and_dashboard(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(
        qtbot, tmp_path, ServerConfiguration("survival", "survival", "paper.jar", 4096, display_name="My World")
    )
    setup.select()

    assert "My World" in setup.window.server_list_view.list_widget.item(0).text()
    assert setup.dashboard.title_label.text() == "My World"
    assert setup.dashboard.title_label.toolTip() == "survival"


# --- edit (M2-GUI-03) ----------------------------------------------------------------------------


def test_arguments_line_round_trips() -> None:
    assert split_arguments('-XX:+UseG1GC "-Dname=My Server"') == ("-XX:+UseG1GC", "-Dname=My Server")
    assert join_arguments(("-XX:+UseG1GC", "-Dname=My Server")) == '-XX:+UseG1GC "-Dname=My Server"'


def test_edit_dialog_saves_the_new_settings(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, SURVIVAL)
    setup.select()

    setup.window.open_edit_dialog()
    dialog = setup.window.edit_dialog
    assert dialog is not None
    dialog.name_edit.setText("Survival Island")
    dialog.memory_spin.setValue(6144)
    dialog.jvm_edit.setText("-XX:+UseG1GC")
    dialog.save()

    stored = setup.repository.items["survival"]
    assert (stored.display_name, stored.memory_mb, stored.jvm_arguments) == ("Survival Island", 6144, ("-XX:+UseG1GC",))
    qtbot.waitUntil(lambda: "Survival Island" in setup.window.server_list_view.list_widget.item(0).text())
    assert setup.window.statusBar().currentMessage() == MESSAGES.text("edit.saved", name="Survival Island")


def test_edit_dialog_shows_domain_errors_and_keeps_the_record(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, SURVIVAL)
    setup.select()
    setup.window.open_edit_dialog()
    dialog = setup.window.edit_dialog
    assert dialog is not None

    dialog.jvm_edit.setText("-Xmx8G")
    dialog.save()

    assert dialog.isVisible() and dialog.error_label.isVisible()
    assert "-Xmx8G" in dialog.error_label.text()
    assert setup.repository.items["survival"] == SURVIVAL


def test_edit_locks_the_jar_while_the_server_runs(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, SURVIVAL)
    setup.coordinator.start_server("survival")
    setup.select()

    setup.window.open_edit_dialog()

    assert setup.window.edit_dialog is not None
    assert not setup.window.edit_dialog.jar_combo.isEnabled()


# --- delete (M2-GUI-04) --------------------------------------------------------------------------


def test_delete_with_files_uses_the_recycle_bin_and_refreshes(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, SURVIVAL, delete_answer=True)
    setup.select()

    qtbot.mouseClick(setup.dashboard.delete_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: setup.window.server_list_view.server_ids() == [])
    assert setup.delete_questions == ["survival"]
    assert setup.remover.removed == ["survival"]
    assert setup.window.statusBar().currentMessage() == MESSAGES.text("delete.done.recycle_bin", name="survival")


def test_cancelled_delete_changes_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, SURVIVAL, delete_answer=None)
    setup.select()

    setup.window.request_delete()

    assert setup.repository.items == {"survival": SURVIVAL}


def test_the_running_server_cannot_be_deleted(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, SURVIVAL, delete_answer=True)
    setup.select()
    setup.coordinator.start_server("survival")
    setup.window.poller.poll_now()  # type: ignore[union-attr]

    assert not setup.dashboard.delete_button.isEnabled()
    setup.window.request_delete()
    assert setup.delete_questions == [] and "survival" in setup.repository.items


# --- folder import (M2-GUI-05) -------------------------------------------------------------------


def test_import_folder_copies_and_selects_the_new_server(qtbot: QtBot, tmp_path: Path) -> None:
    root = tmp_path / "servers"
    root.mkdir()
    source = tmp_path / "old" / "MyServer"
    (source / "world").mkdir(parents=True)
    (source / "world" / "level.dat").write_bytes(b"w" * 3000)
    (source / "paper.jar").write_bytes(b"jar")
    setup = Setup(qtbot, root)

    setup.window.open_adopt_dialog()
    dialog = setup.window.adopt_dialog
    assert dialog is not None
    dialog.load_folder(str(source))
    assert dialog.jar_combo.currentText() == "paper.jar"
    assert dialog.id_edit.text() == "MyServer"
    assert dialog.import_button.isEnabled()
    dialog.submit()

    qtbot.waitUntil(lambda: setup.window.server_list_view.server_ids() == ["MyServer"])
    assert (root / "MyServer" / "world" / "level.dat").read_bytes() == b"w" * 3000
    assert (source / "paper.jar").exists()
    qtbot.waitUntil(lambda: setup.window.adopt_dialog is None)


def test_folder_without_jar_cannot_be_imported(qtbot: QtBot, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    setup = Setup(qtbot, tmp_path / "servers")

    setup.window.open_adopt_dialog()
    dialog = setup.window.adopt_dialog
    assert dialog is not None
    dialog.load_folder(str(empty))

    assert not dialog.import_button.isEnabled()
    assert dialog.location_hint is not None and dialog.location_hint.text() == MESSAGES.text("adopt.no_jars")


# --- settings (M2-GUI-01) ------------------------------------------------------------------------


def test_settings_are_saved_and_applied(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.window.open_settings_dialog()
    dialog = setup.window.settings_dialog
    assert isinstance(dialog, SettingsDialog)

    dialog.stop_spin.setValue(180)
    dialog._pick_java = lambda _parent: "C:/jdk21/bin/java.exe"  # type: ignore[method-assign]
    dialog.choose_java()
    dialog.save()

    assert setup.settings.current.stop_timeout_seconds == 180
    assert setup.settings.current.java_executable == "C:/jdk21/bin/java.exe"
    assert setup.java.configured_executable == "C:/jdk21/bin/java.exe"
    assert JsonApplicationSettingsStore(tmp_path).load().stop_timeout_seconds == 180


def test_settings_refuse_a_java_that_does_not_run(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.window.open_settings_dialog()
    dialog = setup.window.settings_dialog
    assert dialog is not None

    dialog._pick_java = lambda _parent: "C:/broken/java.exe"  # type: ignore[method-assign]
    dialog.choose_java()

    assert dialog.error_label.isVisible()
    assert dialog.java_label.text() == MESSAGES.text("settings.java.auto")


# --- legacy import offer (M2-GUI-02) -------------------------------------------------------------


def test_legacy_servers_are_offered_once_and_imported(qtbot: QtBot, tmp_path: Path) -> None:
    legacy = Legacy(ServerConfiguration("oldworld", "oldworld", "paper.jar", 2048))
    setup = Setup(qtbot, tmp_path, legacy=legacy)

    qtbot.waitUntil(lambda: setup.offers == [1])
    qtbot.waitUntil(lambda: len(setup.results) == 1)
    assert setup.results[0].imported == ("oldworld",)
    qtbot.waitUntil(lambda: setup.window.server_list_view.server_ids() == ["oldworld"])
    assert setup.settings.current.legacy_import_offered

    again = Setup(qtbot, tmp_path, legacy=Legacy(ServerConfiguration("other", "other", "paper.jar", 2048)))
    qtbot.wait(50)
    assert again.offers == []  # offered once only; File › Import from MCServer 0.9.1 stays available


def test_declined_offer_is_remembered_and_imports_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    legacy = Legacy(ServerConfiguration("oldworld", "oldworld", "paper.jar", 2048))
    setup = Setup(qtbot, tmp_path, legacy=legacy, offer_answer=False)

    qtbot.waitUntil(lambda: setup.offers == [1])
    qtbot.wait(50)
    assert setup.results == [] and setup.repository.items == {}
    assert setup.settings.current.legacy_import_offered

    setup.window.import_legacy_action.trigger()
    qtbot.waitUntil(lambda: len(setup.results) == 1)
    assert setup.repository.items["oldworld"].server_id == "oldworld"


def test_no_offer_without_legacy_servers(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    qtbot.wait(50)
    assert setup.offers == []
    assert not setup.settings.current.legacy_import_offered


@pytest.mark.parametrize("key", ["legacy.offer.text"])
def test_offer_text_has_plural_forms(key: str) -> None:
    assert "1 server" in MESSAGES.plural(key, 1)
    assert "3 servers" in MESSAGES.plural(key, 3)


def test_settings_defaults_are_valid() -> None:
    assert ApplicationSettings().stop_timeout_seconds == 90
