"""Dark and light themes: tokens, stylesheet, setting, and switching without a restart (M4)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from test_m2_gui import Setup as M2Setup
from test_m3_gui import Setup as M3Setup

from mcserver.application.settings import ApplicationSettings, InvalidSettings
from mcserver.infrastructure.settings_store import JsonApplicationSettingsStore
from mcserver.presentation import appearance, icons, theme
from mcserver.presentation.app import WindowHost
from mcserver.presentation.dialogs.form import FormDialog
from mcserver.presentation.i18n import messages_for

MESSAGES = messages_for("en")


@pytest.fixture(autouse=True)
def dark_afterwards() -> Iterator[None]:
    """Every test starts and ends in the dark theme, the default."""
    theme.apply(theme.DEFAULT_THEME)
    yield
    theme.apply(theme.DEFAULT_THEME)
    theme.set_arrow_images("", "")
    app = QApplication.instance()
    if isinstance(app, QApplication):
        # apply_appearance also changes the shared palette and colour scheme; later tests expect Qt's defaults.
        QApplication.setPalette(app.style().standardPalette())
        QGuiApplication.styleHints().unsetColorScheme()


# --- tokens and stylesheet ------------------------------------------------------------------


def test_both_palettes_define_the_same_tokens() -> None:
    assert set(theme.DARK) == set(theme.LIGHT)
    for palette in (theme.DARK, theme.LIGHT):
        assert all(re.fullmatch(r"#[0-9a-f]{6}", value) for value in palette.values())


@pytest.mark.parametrize("name", theme.THEMES)
def test_apply_switches_every_token_and_the_stylesheet(name: str) -> None:
    theme.apply(name)
    palette = theme.PALETTES[name]
    assert theme.current == name
    assert all(getattr(theme, token) == value for token, value in palette.items())
    assert theme.CARD == palette["SURFACE_CARD"] and theme.CONSOLE_ERROR == palette["DANGER_TEXT"]
    assert theme.TONE_COLORS["error"] == (palette["DANGER_SUBTLE"], palette["DANGER"], palette["DANGER_TEXT"])
    assert theme.STATUS_COLORS["running"] == palette["ACCENT"]
    # Every colour in the stylesheet comes from the applied palette; nothing is hard-coded.
    used = set(re.findall(r"#[0-9a-fA-F]{6}", theme.STYLESHEET))
    assert used and used <= set(palette.values())


def test_switching_back_restores_the_dark_stylesheet_exactly() -> None:
    dark = theme.STYLESHEET
    theme.apply("light")
    assert theme.STYLESHEET != dark
    theme.apply("dark")
    assert theme.STYLESHEET == dark


def test_unknown_names_fall_back_to_dark() -> None:
    theme.apply("purple")
    assert theme.current == "dark"


@pytest.mark.parametrize(
    ("setting", "system_dark", "expected"),
    [
        ("light", True, "light"),
        ("dark", False, "dark"),
        (None, True, "dark"),
        (None, False, "light"),
        (None, None, "dark"),
        ("purple", False, "light"),
    ],
)
def test_resolve_theme(setting: str | None, system_dark: bool | None, expected: str) -> None:
    assert theme.resolve_theme(setting, system_dark) == expected


def test_icons_and_form_tones_use_the_theme_applied_when_they_are_drawn(qtbot: QtBot) -> None:
    theme.apply("light")
    image = icons.pixmap("check").toImage()
    painted = {image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())}
    assert QColor(theme.LIGHT["TEXT_SECONDARY"]).name() in painted

    dialog = FormDialog("Title", "Subtitle", tone="info")
    qtbot.addWidget(dialog)
    tile = dialog.findChild(type(dialog.error_label), "dialogTone")
    assert tile is not None and theme.LIGHT["INFO_SUBTLE"] in tile.styleSheet()
    assert dialog.styleSheet() == theme.STYLESHEET


# --- the setting ----------------------------------------------------------------------------


def test_theme_setting_is_validated_and_stored(tmp_path: Path) -> None:
    with pytest.raises(InvalidSettings, match="theme"):
        ApplicationSettings(theme="purple")
    store = JsonApplicationSettingsStore(tmp_path)
    store.save(ApplicationSettings(theme="light"))
    assert store.load().theme == "light"
    assert ApplicationSettings().theme is None  # older files: follow Windows


def test_following_windows_never_pins_qt_to_one_scheme(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(appearance, "system_prefers_dark", lambda: False)
    assert appearance.apply_appearance(None) == "light"
    assert theme.current == "light"
    monkeypatch.setattr(appearance, "system_prefers_dark", lambda: True)
    assert appearance.apply_appearance(None) == "dark"
    assert appearance.apply_appearance("light") == "light"


# --- switching in the running app -----------------------------------------------------------


def save_theme(setup: M2Setup, name: str | None) -> None:
    setup.window.open_settings_dialog()
    dialog = setup.window.settings_dialog
    assert dialog is not None
    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))  # the test window is English
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData(name))
    dialog.save()


def test_settings_offer_automatic_dark_and_light(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M2Setup(qtbot, tmp_path)
    setup.window.open_settings_dialog()
    dialog = setup.window.settings_dialog
    assert dialog is not None
    options = [dialog.theme_combo.itemData(index) for index in range(dialog.theme_combo.count())]
    assert options == [None, "dark", "light"]
    assert dialog.theme_combo.currentData() is None


def test_saving_the_light_theme_applies_it_and_rebuilds_the_window(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M2Setup(qtbot, tmp_path)
    with qtbot.waitSignal(setup.window.language_change_requested, timeout=2000) as signal:
        save_theme(setup, "light")
    assert signal.args == ["en"]  # same language, new theme
    assert theme.current == "light"
    assert setup.settings.current.theme == "light"


def test_a_busy_window_postpones_the_theme(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M2Setup(qtbot, tmp_path)
    window = setup.window
    window.open_create_dialog()
    requested: list[str] = []
    window.language_change_requested.connect(requested.append)
    save_theme(setup, "light")
    qtbot.wait(50)
    assert requested == []
    assert theme.current == "dark"  # nothing half-switched
    assert MESSAGES.text("settings.theme.later") in window.notification_texts()


def test_a_windows_mode_change_is_followed_only_in_automatic_mode(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = M2Setup(qtbot, tmp_path)
    window = setup.window
    requested: list[str] = []
    window.language_change_requested.connect(requested.append)
    monkeypatch.setattr(appearance, "system_prefers_dark", lambda: False)

    setup.settings.update(theme="dark", language="en")
    window._on_system_color_scheme(None)  # type: ignore[attr-defined]
    qtbot.wait(50)
    assert requested == [] and theme.current == "dark"

    setup.settings.update(theme=None)
    window._on_system_color_scheme(None)  # type: ignore[attr-defined]
    qtbot.waitUntil(lambda: requested == ["en"])
    assert theme.current == "light"


def test_window_host_rebuilds_the_window_in_the_light_theme(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M3Setup(qtbot, tmp_path)
    setup.select("survival")
    host = WindowHost.__new__(WindowHost)
    host._services = setup.window._services  # type: ignore[attr-defined]
    host.window = setup.window
    theme.apply("light")

    new = host.switch_language("en")
    qtbot.addWidget(new)

    assert new.styleSheet() == theme.STYLESHEET and theme.LIGHT["BG_APP"] in new.styleSheet()
    assert new.dashboard_view.current_tab == setup.window.dashboard_view.current_tab


def test_palette_and_arrows_follow_the_applied_theme(qtbot: QtBot, tmp_path: Path) -> None:
    from PySide6.QtGui import QPalette

    theme.apply("light")
    palette = appearance.theme_palette()
    assert palette.color(QPalette.ColorRole.Window).name() == theme.LIGHT["BG_APP"]
    assert palette.color(QPalette.ColorRole.Text).name() == theme.LIGHT["TEXT"]
    assert palette.color(QPalette.ColorRole.Highlight).name() == theme.LIGHT["ACCENT"]

    down, up = appearance.write_arrow_images(tmp_path)
    assert down.is_file() and up.is_file()
    assert theme.LIGHT["TEXT_SECONDARY"].lstrip("#") in down.name  # one file per colour: never a stale arrow


def test_applying_a_theme_points_the_stylesheet_at_its_arrows(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(appearance, "system_prefers_dark", lambda: None)
    appearance.apply_appearance("light")
    assert "QComboBox::down-arrow" in theme.STYLESHEET
    assert theme.LIGHT["TEXT_SECONDARY"].lstrip("#") in theme.ARROW_DOWN
    appearance.apply_appearance("dark")
    assert theme.DARK["TEXT_SECONDARY"].lstrip("#") in theme.ARROW_DOWN
