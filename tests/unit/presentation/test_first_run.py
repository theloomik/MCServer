"""The first-run guide: when it opens, its steps and what finishing it does (M4-GUI-08)."""

from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot
from test_m2_gui import SURVIVAL, Legacy, Setup

from mcserver.application.settings import SettingsService
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.settings_store import JsonApplicationSettingsStore
from mcserver.presentation.controllers.first_run import Ending, FirstRunController, Step
from mcserver.presentation.dialogs.first_run import FirstRunDialog
from mcserver.presentation.i18n import messages_for

MESSAGES = messages_for()
CREATIVE = ServerConfiguration("creative", "creative", "paper.jar", 2048)


def guide(qtbot: QtBot, root: Path, *servers: ServerConfiguration, legacy: Legacy | None = None) -> Setup:
    setup = Setup(qtbot, root, *servers, legacy=legacy, first_run_guide=True)
    qtbot.wait(10)  # _after_start runs on the first event loop turn
    return setup


def test_guide_opens_on_a_fresh_install_instead_of_the_legacy_offer(qtbot: QtBot, tmp_path: Path) -> None:
    setup = guide(qtbot, tmp_path, legacy=Legacy(SURVIVAL))

    dialog = setup.window.first_run_dialog
    assert isinstance(dialog, FirstRunDialog)
    assert setup.window.page_host.current_page is dialog
    assert setup.offers == []  # the guide's import step replaces the startup offer
    controller = setup.window.first_run_controller
    assert controller is not None
    assert controller.state.steps == (Step.JAVA, Step.FOLDER, Step.IMPORT, Step.CREATE)
    assert controller.state.java is not None and controller.state.java.available


def test_guide_does_not_open_when_servers_exist_or_it_ran_before(qtbot: QtBot, tmp_path: Path) -> None:
    with_servers = guide(qtbot, tmp_path / "a", SURVIVAL)
    assert with_servers.window.first_run_dialog is None

    (tmp_path / "b").mkdir()
    settings = SettingsService(JsonApplicationSettingsStore(tmp_path / "b"), with_servers.java)  # type: ignore[arg-type]
    settings.update(first_run_completed=True)
    ran_before = guide(qtbot, tmp_path / "b")
    assert ran_before.window.first_run_dialog is None
    assert not FirstRunController.should_run(None, 0)


def test_steps_without_legacy_servers_and_back_next(qtbot: QtBot, tmp_path: Path) -> None:
    setup = guide(qtbot, tmp_path)
    dialog = setup.window.first_run_dialog
    controller = setup.window.first_run_controller
    assert dialog is not None and controller is not None
    assert controller.state.steps == (Step.JAVA, Step.FOLDER, Step.CREATE)
    assert dialog.back_button.isHidden()
    assert MESSAGES.text("first_run.java.found", major=21, path="C:/jdk/bin/java.exe") == dialog.java_banner.text.text()

    dialog.next_button.click()
    assert controller.state.step is Step.FOLDER and dialog.folder_path.text() == str(tmp_path)
    dialog.back_button.click()
    assert controller.state.step is Step.JAVA
    dialog.next_button.click()
    dialog.next_button.click()
    assert controller.state.is_last and dialog.next_button.text() == MESSAGES.text("first_run.finish")
    assert dialog.skip_button.isHidden()

    dialog.next_button.click()
    qtbot.waitUntil(lambda: setup.window.first_run_dialog is None)
    assert setup.settings.current.first_run_completed
    assert setup.window.page_host.current_page is None


def test_choose_java_stores_it_and_a_broken_one_is_explained(qtbot: QtBot, tmp_path: Path) -> None:
    setup = guide(qtbot, tmp_path)
    controller = setup.window.first_run_controller
    dialog = setup.window.first_run_dialog
    assert controller is not None and dialog is not None

    controller.choose_java("C:/broken/java.exe")
    assert controller.state.java_error is not None
    assert dialog.java_banner.property("tone") == "error"
    controller.choose_java("C:/jdk-21/bin/java.exe")
    assert controller.state.java_error is None
    assert setup.settings.current.java_executable == "C:/jdk-21/bin/java.exe"


def test_import_step_imports_inline_and_the_guide_remembers_the_offer(qtbot: QtBot, tmp_path: Path) -> None:
    setup = guide(qtbot, tmp_path, legacy=Legacy(SURVIVAL, CREATIVE))
    controller = setup.window.first_run_controller
    dialog = setup.window.first_run_dialog
    assert controller is not None and dialog is not None
    controller.next()
    controller.next()
    assert controller.state.step is Step.IMPORT
    assert dialog.import_intro.text() == MESSAGES.plural("first_run.import.intro", 2)

    dialog.import_button.click()
    qtbot.waitUntil(lambda: controller.state.import_result is not None)
    assert controller.state.import_result.imported_count == 2  # type: ignore[union-attr]
    assert setup.results == []  # shown on the page, not as a second result page
    assert not dialog.import_button.isEnabled()
    qtbot.waitUntil(lambda: len(setup.window.server_list_controller.state.servers) == 2)

    controller.next()
    assert dialog.create_intro.text() == MESSAGES.text("first_run.create.has_servers")
    assert setup.settings.current.legacy_import_offered


def test_skip_and_create_server_endings(qtbot: QtBot, tmp_path: Path) -> None:
    setup = guide(qtbot, tmp_path, legacy=Legacy(SURVIVAL))
    dialog = setup.window.first_run_dialog
    assert dialog is not None
    dialog.skip_button.click()
    qtbot.waitUntil(lambda: setup.window.first_run_dialog is None)
    assert setup.settings.current.first_run_completed and setup.settings.current.legacy_import_offered
    assert len(setup.window.server_list_controller.state.servers) == 0  # skipping imports nothing

    setup.window.first_run_action.trigger()  # File › Setup guide opens it again
    dialog = setup.window.first_run_dialog
    controller = setup.window.first_run_controller
    assert dialog is not None and controller is not None
    while not controller.state.is_last:
        controller.next()
    dialog.create_server_button.click()
    qtbot.waitUntil(lambda: setup.window.create_dialog is not None)
    assert controller.state.finished is Ending.CREATE_SERVER


def test_every_guide_text_exists_in_both_languages() -> None:
    for language in ("en", "uk"):
        messages = messages_for(language)
        for step in Step:
            assert messages.text(f"first_run.{step.value}.title") != f"first_run.{step.value}.title"
        assert messages.plural("first_run.import.intro", 5) != "first_run.import.intro"
