"""Dialogs open modally over the dimmed window; Settings opens as a page in the content area (UX overhaul)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from pytestqt.qtbot import QtBot
from test_m3_gui import MESSAGES, Setup

from mcserver.presentation.dialogs.confirm_dialog import Choice, ConfirmDialog, ask
from mcserver.presentation.dialogs.prompt_dialog import PromptDialog, PromptField


def test_create_dialog_opens_modally_over_the_dimmed_window(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    window = setup.window
    window.show()
    window.open_create_dialog()
    dialog = window.create_dialog
    assert dialog is not None
    assert window.page_host.current_page is dialog
    assert not dialog.isWindow()  # inside the window, not a separate one
    assert window.page_host.isVisible() and dialog.isVisible()
    assert window.server_list_view.isVisible() and not window.server_list_view.isEnabled()  # behind the dimming
    assert not window.new_server_action.isEnabled()  # shortcuts pause while a dialog is open
    card = dialog.parentWidget()
    while card is not None and card.objectName() != "modalCard":
        card = card.parentWidget()
    assert card is not None and card.width() < window.width()  # sized to the dialog, not the window
    assert card.findChild(type(dialog.footer), "dialogFooter") is dialog.footer  # buttons outside the scrolling part
    dialog.reject()
    assert window.page_host.current_page is None and window.page_host.isHidden()
    assert window.server_list_view.isEnabled() and window.new_server_action.isEnabled()


def test_settings_open_as_a_page_with_the_server_list_visible(qtbot: QtBot, tmp_path: Path) -> None:
    from test_m2_gui import Setup as M2Setup

    setup = M2Setup(qtbot, tmp_path)
    window = setup.window
    window.open_settings_dialog()
    page = window.settings_dialog
    assert page is not None and window.content_host.current_page is page
    assert window.server_list_view.isVisible() and window.server_list_view.isEnabled()
    assert not window.dashboard_view.isVisible()
    page.reject()
    assert window.content_host.currentWidget() is window.dashboard_view


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
