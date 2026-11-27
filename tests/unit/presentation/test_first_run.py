"""The first-run guide: when it opens, its steps and what finishing it does (M4-GUI-08)."""

from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot
from test_m2_gui import SURVIVAL, Setup

from mcserver.application.settings import SettingsService
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.settings_store import JsonApplicationSettingsStore
from mcserver.presentation.controllers.first_run import Ending, FirstRunController, Step
from mcserver.presentation.dialogs.first_run import FirstRunDialog
from mcserver.presentation.i18n import messages_for

MESSAGES = messages_for()


def guide(qtbot: QtBot, root: Path, *servers: ServerConfiguration) -> Setup:
    setup = Setup(qtbot, root, *servers, first_run_guide=True)
    qtbot.wait(10)  # _after_start runs on the first event loop turn
    return setup


def test_guide_opens_on_a_fresh_install(qtbot: QtBot, tmp_path: Path) -> None:
    setup = guide(qtbot, tmp_path)

    dialog = setup.window.first_run_dialog
    assert isinstance(dialog, FirstRunDialog)
    assert setup.window.page_host.current_page is dialog
    controller = setup.window.first_run_controller
    assert controller is not None
    assert controller.state.steps == (Step.JAVA, Step.FOLDER, Step.CREATE)
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


def test_steps_back_next_and_finish(qtbot: QtBot, tmp_path: Path) -> None:
    setup = guide(qtbot, tmp_path)
    dialog = setup.window.first_run_dialog
    controller = setup.window.first_run_controller
    assert dialog is not None and controller is not None
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


def test_skip_then_reopen_from_settings_and_create_a_server(qtbot: QtBot, tmp_path: Path) -> None:
    setup = guide(qtbot, tmp_path)
    dialog = setup.window.first_run_dialog
    assert dialog is not None
    dialog.skip_button.click()
    qtbot.waitUntil(lambda: setup.window.first_run_dialog is None)
    assert setup.settings.current.first_run_completed

    setup.window.open_settings_dialog()  # Settings › Setup guide opens it again
    settings_page = setup.window.settings_dialog
    assert settings_page is not None
    settings_page.setup_guide_button.click()
    dialog = setup.window.first_run_dialog
    controller = setup.window.first_run_controller
    assert dialog is not None and controller is not None
    while not controller.state.is_last:
        controller.next()
    dialog.create_server_button.click()
    qtbot.waitUntil(lambda: setup.window.create_dialog is not None)
    assert controller.state.finished is Ending.CREATE_SERVER
    assert setup.window.content_host.current_page is None  # back from Settings to the servers


def test_every_guide_text_exists_in_both_languages() -> None:
    for language in ("en", "uk"):
        messages = messages_for(language)
        for step in Step:
            assert messages.text(f"first_run.{step.value}.title") != f"first_run.{step.value}.title"
        assert "0.9.1" not in " ".join(messages.text(f"first_run.{step.value}.title") for step in Step)
