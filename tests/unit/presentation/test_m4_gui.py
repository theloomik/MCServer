"""M4 UI: Server menu mirrors the toolbar, Properties keeps refused edits, sidebar and welcome actions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QLineEdit, QSpinBox
from pytestqt.qtbot import QtBot
from test_m3_gui import MESSAGES, Setup

from mcserver.presentation import icons


def test_server_actions_sit_beside_the_tabs_with_readable_names(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.dashboard_view
    assert view.tabs.cornerWidget() is not None
    for button, key in (
        (view.open_folder_button, "dashboard.open_folder"),
        (view.open_logs_button, "dashboard.open_logs"),
        (view.edit_button, "dashboard.edit"),
        (view.delete_button, "dashboard.delete"),
    ):
        assert button.accessibleName() == MESSAGES.text(key)
        assert view.tabs.cornerWidget().isAncestorOf(button)
    assert view.start_button.isEnabled() and not view.stop_button.isEnabled()
    assert view.kill_button.isHidden()  # Kill is only offered while stopping


def test_refused_property_save_keeps_the_typed_values(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.properties_view
    assert view is not None
    assert not view.save_button.isEnabled() and view.unsaved_label.text() == ""
    view.editors["view-distance"].setText("far")  # type: ignore[union-attr]
    view.editors["motd"].setText("Changed")  # type: ignore[union-attr]
    assert view.unsaved_label.text() == MESSAGES.plural("properties.unsaved", 2)
    assert view.save_button.isEnabled()

    view.save_button.click()

    editor = view.editors["view-distance"]
    assert isinstance(editor, QLineEdit) and editor.text() == "far"
    assert editor.property("invalid") is True
    motd = view.editors["motd"]
    assert isinstance(motd, QLineEdit) and motd.text() == "Changed"
    assert view.unsaved_label.text() == MESSAGES.plural("properties.unsaved", 2)


def test_saved_properties_clear_the_unsaved_count(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.properties_view
    assert view is not None
    spin = view.editors["max-players"]
    assert isinstance(spin, QSpinBox)
    spin.setValue(30)
    view.save_button.click()
    assert view.unsaved_label.text() == "" and not view.save_button.isEnabled()


def test_sidebar_and_welcome_open_import_and_settings(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    window = setup.window
    opened: list[str] = []
    window.open_adopt_dialog = lambda: opened.append("adopt")  # type: ignore[method-assign]
    window.open_settings_dialog = lambda: opened.append("settings")  # type: ignore[method-assign]
    window.open_create_dialog = lambda: opened.append("create")  # type: ignore[method-assign]
    # Signals were connected to the bound methods at construction; emit through the views instead.
    window.server_list_view.import_requested.disconnect()
    window.server_list_view.import_requested.connect(window.open_adopt_dialog)
    window.server_list_view.settings_requested.disconnect()
    window.server_list_view.settings_requested.connect(window.open_settings_dialog)
    window.dashboard_view.new_server_requested.disconnect()
    window.dashboard_view.new_server_requested.connect(window.open_create_dialog)
    window.server_list_view.import_button.click()
    window.server_list_view.settings_button.click()
    window.dashboard_view.welcome_new_button.click()
    assert opened == ["adopt", "settings", "create"]
    assert window.server_list_view.caption.text() == MESSAGES.text("server_list.title_count", count=2).upper()


def test_icons_render_every_name() -> None:
    for name in icons.NAMES:
        assert not icons.pixmap(name).isNull()
