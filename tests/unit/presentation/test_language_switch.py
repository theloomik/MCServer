"""Changing the language in Settings rebuilds the window in that language without a restart (M4-GUI-02)."""

from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot
from test_m2_gui import Setup as M2Setup
from test_m3_gui import Setup as M3Setup

from mcserver.presentation.app import WindowHost
from mcserver.presentation.i18n import messages_for


def save_language(setup: M2Setup, language: str) -> None:
    setup.window.open_settings_dialog()
    dialog = setup.window.settings_dialog
    assert dialog is not None
    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData(language))
    dialog.save()


def test_saving_another_language_requests_a_rebuild(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M2Setup(qtbot, tmp_path)
    assert setup.window.language == "en"
    with qtbot.waitSignal(setup.window.language_change_requested, timeout=2000) as signal:
        save_language(setup, "uk")
    assert signal.args == ["uk"]


def test_a_busy_window_postpones_the_change(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M2Setup(qtbot, tmp_path)
    window = setup.window
    window.open_create_dialog()  # an open page would be lost by a rebuild
    requested: list[str] = []
    window.language_change_requested.connect(requested.append)
    save_language(setup, "uk")
    qtbot.wait(50)
    assert requested == []
    assert window.statusBar().currentMessage() == messages_for("en").text("settings.language.later")


def test_window_host_rebuilds_in_the_new_language_and_keeps_the_view(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M3Setup(qtbot, tmp_path)
    services = setup.window._services  # the same backend serves the new window
    host = WindowHost(services, messages_for("en"))
    old = host.window
    qtbot.addWidget(old)
    old.show()
    old.server_list_controller.select("survival")
    old.dashboard_view.show_tab("backups")

    new = host.switch_language("uk")
    qtbot.addWidget(new)

    assert host.window is new and new is not old
    assert new.language == "uk" and new.windowTitle() == messages_for("uk").text("app.title")
    assert new.menuBar().actions()[0].text() == messages_for("uk").text("menu.file")
    row = new.dashboard_controller.state.row
    assert row is not None and row.server_id == "survival"
    assert new.dashboard_view.current_tab == "backups"
    assert not old.isVisible() and new.isVisible()
    assert old.poller is None or not old.poller.active  # the old window stopped polling
