"""Accessibility checks that can be automated (M4-GUI-07); the rest is docs/qa/usability-checklist.md."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest
import test_m2_gui
import test_m3_gui
from accessibility import unnamed_controls, unreachable_controls
from PySide6.QtWidgets import QApplication, QDialog
from pytestqt.qtbot import QtBot

from mcserver.application.errors import JavaNotFound
from mcserver.presentation import theme
from mcserver.presentation.dialogs.java_setup_dialog import JavaSetupDialog
from mcserver.presentation.dialogs.prompt_dialog import PromptDialog, PromptField
from mcserver.presentation.errors import UserMessage
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.main_window import MainWindow

MESSAGES = messages_for()


# --- names and keyboard reach ---------------------------------------------------------------


def test_every_tab_of_the_main_window_has_named_reachable_controls(qtbot: QtBot, tmp_path: Path) -> None:
    setup = test_m3_gui.Setup(qtbot, tmp_path)
    setup.select("survival")
    window = setup.window
    for tab in window.dashboard_view.tab_keys:
        window.dashboard_view.show_tab(tab)
        assert unnamed_controls(window) == [], tab
        assert unreachable_controls(window) == [], tab


def _pages(window: MainWindow) -> dict[str, Callable[[], object]]:
    return {
        "create": window.open_create_dialog,
        "edit": window.open_edit_dialog,
        "adopt": window.open_adopt_dialog,
        "settings": window.open_settings_dialog,
        "first_run": window.open_first_run,
        "details": lambda: window.show_details(UserMessage("errors.unexpected", {}, "Traceback ...")),
        "prompt": lambda: window.show_page(
            PromptDialog("Title", [PromptField("name", "Name")], "OK", "Cancel", window)
        ),
        "java": lambda: window.show_page(
            JavaSetupDialog(JavaNotFound(), window._services.java, MESSAGES, window)  # type: ignore[arg-type]
        ),
    }


@pytest.mark.parametrize("page", ["create", "edit", "adopt", "settings", "first_run", "details", "prompt", "java"])
def test_every_page_has_named_reachable_controls(qtbot: QtBot, tmp_path: Path, page: str) -> None:
    setup = test_m2_gui.Setup(qtbot, tmp_path, test_m2_gui.SURVIVAL)
    setup.select()
    window = setup.window

    _pages(window)[page]()

    current = window.page_host.current_page
    assert current is not None
    assert unnamed_controls(current) == []
    assert unreachable_controls(current) == []


def test_form_labels_name_their_fields(qtbot: QtBot, tmp_path: Path) -> None:
    setup = test_m2_gui.Setup(qtbot, tmp_path, test_m2_gui.SURVIVAL)
    setup.window.open_create_dialog()
    dialog = setup.window.create_dialog
    assert dialog is not None
    assert dialog.server_id_edit.accessibleName() == MESSAGES.text("create.server_id.label")
    assert dialog.server_id_edit.accessibleDescription() == MESSAGES.text("create.server_id.hint")


# --- keyboard ---------------------------------------------------------------------------------


def test_shortcuts_reach_every_tab_the_server_list_and_the_console(qtbot: QtBot, tmp_path: Path) -> None:
    setup = test_m3_gui.Setup(qtbot, tmp_path)
    setup.select("survival")
    window = setup.window
    keys = window.dashboard_view.tab_keys
    for number, key in enumerate(keys, start=1):
        action = window.tab_actions[key]
        assert action.shortcut().toString() == f"Ctrl+{number}"
        action.trigger()
        assert window.dashboard_view.current_tab == key

    window.activateWindow()
    window.focus_list_action.trigger()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is window.server_list_view.list_widget)
    window.dashboard_view.show_tab("backups")
    window.focus_console_action.trigger()
    assert window.dashboard_view.current_tab == "overview"
    console = window.dashboard_view.console
    qtbot.waitUntil(lambda: QApplication.focusWidget() in (console.input, console.text))
    assert window.settings_action.shortcut().toString() == "Ctrl+,"


def test_a_page_focuses_its_first_field_and_gives_the_focus_back(qtbot: QtBot, tmp_path: Path) -> None:
    setup = test_m2_gui.Setup(qtbot, tmp_path, test_m2_gui.SURVIVAL)
    window = setup.window
    window.activateWindow()
    window.focus_list_action.trigger()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is window.server_list_view.list_widget)

    window.open_create_dialog()
    dialog = window.create_dialog
    assert dialog is not None
    qtbot.waitUntil(lambda: QApplication.focusWidget() is dialog.server_id_edit)

    dialog.reject()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is window.server_list_view.list_widget)


def test_escape_closes_a_page(qtbot: QtBot, tmp_path: Path) -> None:
    setup = test_m2_gui.Setup(qtbot, tmp_path, test_m2_gui.SURVIVAL)
    window = setup.window
    window.show_details(UserMessage("errors.unexpected", {}, "trace"))
    page = window.page_host.current_page
    assert isinstance(page, QDialog)
    focused = QApplication.focusWidget() or page
    qtbot.keyClick(focused, "\x1b")  # Esc
    qtbot.waitUntil(lambda: window.page_host.current_page is None)


def test_focus_is_styled_for_every_kind_of_control() -> None:
    sheet = theme.STYLESHEET
    for selector in (
        "QPushButton#primaryButton:focus",
        "QPushButton#secondaryButton:focus",
        "QPushButton#dangerButton:focus",
        "QPushButton#ghostButton:focus",
        "QPushButton#iconButton:focus",
        "QPushButton#linkButton:focus",
        "QComboBox:focus",
        "QCheckBox::indicator:focus",
        "QLineEdit:focus",
        "QTabBar::tab:focus",
    ):
        assert selector in sheet, selector


# --- contrast (WCAG 2.1) ----------------------------------------------------------------------


def _luminance(color: str) -> float:
    channels = [int(color.lstrip("#")[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio of two ``#rrggbb`` colours."""
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


SURFACES = {
    "app": theme.BG_APP,
    "sidebar": theme.BG_SIDEBAR,
    "card": theme.SURFACE_CARD,
    "raised": theme.SURFACE_RAISED,
    "hover": theme.SURFACE_HOVER,
    "console": theme.SURFACE_CONSOLE,
}


@pytest.mark.parametrize(
    "name", ["TEXT", "TEXT_SECONDARY", "TEXT_MUTED", "CONSOLE_TEXT", "CONSOLE_TIMESTAMP", "DANGER_TEXT", "INFO"]
)
def test_text_colours_reach_aa_on_every_surface(name: str) -> None:
    color = getattr(theme, name)
    for surface, background in SURFACES.items():
        if name.startswith("CONSOLE_") and surface != "console":
            continue  # console colours are only drawn on the console background
        assert contrast(color, background) >= 4.5, (name, surface)


def test_banner_and_button_text_reach_aa() -> None:
    for tone, (background, _border, foreground) in theme.TONE_COLORS.items():
        assert contrast(foreground, background) >= 4.5, tone
        assert contrast(theme.TEXT, background) >= 4.5, tone
    assert contrast(theme.TEXT_ON_ACCENT, theme.ACCENT) >= 4.5
    assert contrast(theme.DANGER_TEXT, theme.DANGER_SUBTLE) >= 4.5


def test_focus_and_status_marks_reach_the_non_text_minimum() -> None:
    for background in SURFACES.values():
        assert contrast(theme.FOCUS, background) >= 3
        for color in theme.STATUS_COLORS.values():
            assert contrast(color, background) >= 3


@pytest.mark.skipif(not os.environ.get("QT_QPA_FONTDIR"), reason="text widths need the real fonts")
@pytest.mark.parametrize("language", ["en", "uk"])
def test_the_window_fits_a_small_screen_at_150_percent(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    # 1366 x 768 at 125 % leaves about 1093 x 535 logical pixels for the window (taskbar and title bar off);
    # 1920 x 1080 at 150 % leaves 1280 x 640. The width also fits 1366 at 150 % (910 logical pixels).
    monkeypatch.setattr(test_m3_gui, "MESSAGES", messages_for(language))
    setup = test_m3_gui.Setup(qtbot, tmp_path)
    setup.select("survival")
    window = setup.window
    for tab in window.dashboard_view.tab_keys:
        window.dashboard_view.show_tab(tab)
        minimum = window.minimumSizeHint()
        assert minimum.width() <= 910 and minimum.height() <= 535, (tab, minimum)


def test_narrow_windows_stack_the_inspector_and_wrap_the_schedule(qtbot: QtBot, tmp_path: Path) -> None:
    setup = test_m3_gui.Setup(qtbot, tmp_path)
    setup.select("survival")
    window = setup.window
    window.resize(1400, 800)
    qtbot.waitUntil(lambda: not window.dashboard_view.overview.stacked)
    window.resize(900, 600)
    qtbot.waitUntil(lambda: window.dashboard_view.overview.stacked)
    assert window.dashboard_view.inspector.height() <= window.dashboard_view.overview.STACKED_INSPECTOR_HEIGHT

    backups = window.backups_view
    assert backups is not None
    window.dashboard_view.show_tab("backups")
    row = backups.schedule_row
    row.resize(row.minimumSizeHint().width(), row.height())
    qtbot.waitUntil(lambda: row.wrapped)
    row.resize(2000, row.height())
    qtbot.waitUntil(lambda: not row.wrapped)


def test_ukrainian_names_exist_for_every_accessibility_key() -> None:
    english, ukrainian = messages_for("en"), messages_for("uk")
    for key in (
        "a11y.server_list",
        "a11y.console_output",
        "a11y.console_command",
        "a11y.console_filter",
        "menu.view",
        "menu.view.server_list",
        "menu.view.console",
    ):
        assert ukrainian.text(key) not in (key, english.text(key))
