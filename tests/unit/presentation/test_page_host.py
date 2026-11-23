"""Dialogs open as pages in the main window's content area; the sidebar stays visible (M4 design)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from pytestqt.qtbot import QtBot
from test_m3_gui import MESSAGES, Setup

from mcserver.presentation.dialogs.confirm_dialog import Choice, ConfirmDialog, ask
from mcserver.presentation.dialogs.prompt_dialog import PromptDialog, PromptField


def test_create_dialog_opens_in_the_content_area_with_the_sidebar_visible(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    window = setup.window
    window.open_create_dialog()
    dialog = window.create_dialog
    assert dialog is not None
    assert window.page_host.current_page is dialog
    assert not dialog.isWindow()  # embedded, not a separate window
    assert window.server_list_view.isVisible() and dialog.isVisible()
    assert not window.dashboard_view.isVisible()

    dialog.reject()
    assert window.page_host.current_page is None
    assert window.page_host.currentWidget() is window.dashboard_view


def test_pages_stack_and_return_to_the_page_below(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    window = setup.window
    window.open_create_dialog()
    create = window.create_dialog
    answers: list[str | None] = []

    def answer() -> None:
        top = window.page_host.current_page
        assert isinstance(top, ConfirmDialog) and top is not create
        top.buttons["yes"].click()

    QTimer.singleShot(0, answer)
    answers.append(ask(window, "Question?", "Text", [Choice("no", "No"), Choice("yes", "Yes", "primary")]))
    assert answers == ["yes"]
    assert window.page_host.current_page is create


def test_picking_another_server_closes_open_pages(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    window = setup.window
    setup.select("survival")
    window.open_edit_dialog()
    assert window.page_host.pages
    window.server_list_view.list_widget.setCurrentRow(window.server_list_view.server_ids().index("creative"))
    assert not window.page_host.pages
    row = window.dashboard_controller.state.row
    assert row is not None and row.server_id == "creative"


def test_prompt_page_returns_the_typed_values(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    window = setup.window
    dialog = PromptDialog(
        MESSAGES.text("worlds.new.title"),
        [PromptField("name", "Name"), PromptField("seed", "Seed", optional=True)],
        "Create",
        "Cancel",
        window,
    )

    def type_and_submit() -> None:
        assert window.page_host.current_page is dialog
        assert not dialog.ok_button.isEnabled()  # the name is required
        dialog.edits["name"].setText("  lobby ")
        dialog.ok_button.click()

    QTimer.singleShot(0, type_and_submit)
    assert window.run_page(dialog) == PromptDialog.DialogCode.Accepted
    assert dialog.values == {"name": "lobby", "seed": ""}
