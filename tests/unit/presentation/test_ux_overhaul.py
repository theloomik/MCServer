"""UX overhaul: wheel behaviour, memory slider, grouped properties, dashboard tiles, settings page, no 0.9.1."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QComboBox, QScrollArea, QSpinBox, QVBoxLayout, QWidget
from pytestqt.qtbot import QtBot
from test_m2_gui import SURVIVAL
from test_m2_gui import Setup as M2Setup
from test_m3_gui import Setup as M3Setup

from mcserver.application.server_metrics import ServerMetricsSnapshot
from mcserver.domain.lifecycle import ServerState
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.views.memory_slider import MemorySlider, format_gb, memory_limits
from mcserver.presentation.wheel_guard import install_wheel_guard

MESSAGES = messages_for("en")
LOCALES = Path(__file__).resolve().parents[3] / "src/mcserver/presentation/i18n/locales"


# --- mouse wheel ----------------------------------------------------------------------------


def _wheel(widget: QWidget, steps: int = 1) -> None:
    centre = QPointF(widget.rect().center())
    event = QWheelEvent(
        centre,
        QPointF(widget.mapToGlobal(QPoint(int(centre.x()), int(centre.y())))),
        QPoint(0, 0),
        QPoint(0, 120 * steps),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)


def test_the_wheel_scrolls_the_page_instead_of_changing_an_unfocused_value(qtbot: QtBot) -> None:
    install_wheel_guard()
    scroll = QScrollArea()
    qtbot.addWidget(scroll)
    page = QWidget()
    layout = QVBoxLayout(page)
    spin = QSpinBox()
    spin.setRange(0, 100)
    spin.setValue(50)
    combo = QComboBox()
    combo.addItems(["a", "b", "c"])
    layout.addWidget(spin)
    layout.addWidget(combo)
    layout.addSpacing(2000)
    scroll.setWidget(page)
    scroll.resize(300, 200)
    scroll.show()

    _wheel(spin, -1)
    _wheel(combo, -1)
    assert spin.value() == 50 and combo.currentIndex() == 0  # unchanged
    assert scroll.verticalScrollBar().value() > 0  # the page scrolled instead
    assert spin.focusPolicy() == Qt.FocusPolicy.StrongFocus  # the wheel never takes the focus

    spin.setFocus()
    qtbot.waitUntil(spin.hasFocus)
    _wheel(spin, 1)
    assert spin.value() == 51  # after clicking in, the wheel changes the value on purpose


# --- memory slider --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("total_mb", "maximum", "default"),
    [(4096, 2, 2), (8192, 6, 2), (16384, 12, 2), (32768, 24, 2), (131072, 32, 2), (2048, 1, 1), (None, 6, 2)],
)
def test_memory_limits_leave_room_for_windows(total_mb: int | None, maximum: int, default: int) -> None:
    limits = memory_limits(total_mb)
    assert (limits.maximum_gb, limits.default_gb) == (maximum, default)


def test_slider_shows_gigabytes_and_offers_common_sizes(qtbot: QtBot) -> None:
    slider = MemorySlider(MESSAGES, 16384)
    qtbot.addWidget(slider)
    assert slider.value_mb() == 2048
    assert slider.value_label.text() == MESSAGES.text("memory.gb", value="2")
    assert (slider.slider.minimum(), slider.slider.maximum()) == (1, 12)
    chips = {slider.presets.id(chip): chip for chip in slider.presets.buttons()}
    assert sorted(chips) == [2, 4, 8]  # 16 GB is more than this PC can spare
    chips[8].click()
    assert slider.value_mb() == 8192 and chips[8].isChecked() and not chips[2].isChecked()
    slider.slider.setValue(4)  # the slider and the quick choices stay in step both ways
    assert chips[4].isChecked() and not chips[8].isChecked()
    slider.slider.setValue(3)
    assert not any(chip.isChecked() for chip in chips.values())
    assert slider.slider.accessibleName() == MESSAGES.text("memory.label")


def test_the_slider_moves_in_whole_gigabytes_with_a_mark_for_each(qtbot: QtBot) -> None:
    slider = MemorySlider(MESSAGES, 16384)
    qtbot.addWidget(slider)
    slider.resize(520, slider.sizeHint().height())
    slider.show()
    bar = slider.slider
    assert (bar.singleStep(), bar.pageStep()) == (1, 1)
    assert slider.ticks.labelled_values() == list(range(1, 13))  # 12 marks, all numbered at this width
    third = bar.position_of(3)
    assert bar.value_at(third + 4) == 3 and bar.value_at(third - 4) == 3  # a click near a mark snaps to it
    qtbot.mouseClick(bar, Qt.MouseButton.LeftButton, pos=QPoint(int(bar.position_of(7)), bar.height() // 2))
    assert bar.value() == 7 and slider.value_mb() == 7 * 1024
    qtbot.keyClick(bar, Qt.Key.Key_Right)
    assert slider.value_mb() == 8 * 1024  # the arrow keys move one gigabyte


def test_crowded_marks_number_only_every_few_steps(qtbot: QtBot) -> None:
    slider = MemorySlider(MESSAGES, 128 * 1024)  # 32 GB range
    qtbot.addWidget(slider)
    slider.resize(360, slider.sizeHint().height())
    slider.show()
    labelled = slider.ticks.labelled_values()
    assert labelled[0] == 1 and labelled[-1] == 32 and len(labelled) < 32
    assert slider.ticks.label_step() > 1


@pytest.mark.parametrize(("total_mb", "maximum", "value", "chips"), [(2048, 1, 1024, False), (4096, 2, 2048, False)])
def test_a_small_pc_gets_a_safe_default_and_no_needless_quick_choices(
    qtbot: QtBot, total_mb: int, maximum: int, value: int, chips: bool
) -> None:
    slider = MemorySlider(MESSAGES, total_mb)
    qtbot.addWidget(slider)
    assert slider.slider.maximum() == maximum and slider.value_mb() == value
    assert bool(slider.presets.buttons()) is chips  # with so few steps the marks are enough


def test_an_existing_unusual_value_is_kept_until_the_slider_moves(qtbot: QtBot) -> None:
    slider = MemorySlider(MESSAGES, 8192, 4608)  # 4.5 GB, set before the slider existed
    qtbot.addWidget(slider)
    assert slider.value_mb() == 4608
    slider.slider.setValue(3)
    assert slider.value_mb() == 3072


def test_a_value_above_the_recommendation_stays_selectable_and_is_flagged(qtbot: QtBot) -> None:
    slider = MemorySlider(MESSAGES, 8192, 16384)
    qtbot.addWidget(slider)
    assert slider.slider.maximum() == 16 and slider.value_mb() == 16384
    assert slider.value_label.property("warning") is True
    assert slider.range_label.text() == MESSAGES.text("memory.over", maximum=6)
    assert format_gb(1536) == "1.5" and format_gb(2048) == "2"


def test_create_dialog_uses_the_pcs_memory(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M2Setup(qtbot, tmp_path)
    setup.window._services.system_memory_mb = 32768  # type: ignore[attr-defined]
    setup.window.open_create_dialog()
    dialog = setup.window.create_dialog
    assert dialog is not None
    assert dialog.memory_slider.slider.maximum() == 24 and dialog.memory_mb == 2048


# --- properties -----------------------------------------------------------------------------


def test_properties_are_grouped_with_readable_names_and_searchable_by_either(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M3Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.properties_view
    assert view is not None
    groups = [heading.findChild(QWidget).text() for heading, _frame, _keys in view._groups]  # type: ignore[attr-defined]
    assert groups[0] == MESSAGES.text("properties.group.common").upper()
    assert view.editors["motd"].accessibleName() == MESSAGES.text("properties.label.motd")
    assert view.editors["motd"].accessibleDescription() == "motd"  # the technical name stays available

    view.filter_edit.setText(MESSAGES.text("properties.label.max-players")[:7])  # by the readable name
    assert not view._cells["max-players"].isHidden() and view._cells["motd"].isHidden()  # type: ignore[attr-defined]
    view.filter_edit.setText("view-dist")  # by the key
    assert not view._cells["view-distance"].isHidden()  # type: ignore[attr-defined]


def test_unknown_properties_wait_in_a_collapsed_group_that_search_opens(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M3Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.properties_view
    assert view is not None and view.other_button is not None
    other = [frame for heading, frame, _keys in view._groups if heading.isAncestorOf(view.other_button)][0]  # type: ignore[attr-defined]
    assert other.isHidden() and not view.other_button.isChecked()
    view.other_button.click()
    assert not other.isHidden()
    view.other_button.click()
    unknown = [key for key in view.editors if key not in ("motd", "difficulty", "max-players", "pvp", "view-distance")]
    view.filter_edit.setText(unknown[0])
    assert not other.isHidden()  # a search reaches rare keys too


class _WindowWatcher(QObject):
    """Records every widget shown as a window of its own (a stray one flashes on screen as a small frame)."""

    def __init__(self) -> None:
        super().__init__()
        self.shown: list[str] = []

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if event.type() == QEvent.Type.Show and isinstance(watched, QWidget) and watched.isWindow():
            self.shown.append(f"{type(watched).__name__} {watched.objectName()!r}")
        return False


def test_switching_servers_opens_no_stray_windows(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M3Setup(qtbot, tmp_path)
    watcher = _WindowWatcher()
    app = QApplication.instance()
    assert app is not None
    app.installEventFilter(watcher)
    try:
        setup.select("survival")
        setup.window.dashboard_view.tabs.setCurrentIndex(1)  # the properties page builds a row per key
        qtbot.wait(20)
    finally:
        app.removeEventFilter(watcher)
    assert watcher.shown == []


# --- dashboard ------------------------------------------------------------------------------


def test_stopped_and_running_states_are_clear_at_a_glance(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M3Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.dashboard_view
    assert view.hint_label.text() == MESSAGES.text("dashboard.hint.stopped")
    assert view.tiles["memory"].detail.text() == MESSAGES.text("metrics.not_running")
    assert view.players_label.text() == MESSAGES.text("metrics.players_none")

    setup.metrics.snapshot = ServerMetricsSnapshot("survival", ServerState.RUNNING, 30.0, 1024.0, 4096, 75)
    setup.window.sample_metrics()
    assert view.metric_values["memory"].text() == MESSAGES.text("metrics.memory_gb", used="1")
    assert view.tiles["memory"].detail.text() == MESSAGES.text("metrics.memory_of", allocated="4")
    assert view.metric_values["uptime"].text() == "0:01:15"


# --- settings -------------------------------------------------------------------------------


def test_settings_page_groups_appearance_java_servers_and_help(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M2Setup(qtbot, tmp_path)
    setup.window.open_settings_dialog()
    page = setup.window.settings_dialog
    assert page is not None
    assert page.java_status.text() == MESSAGES.text("settings.java.found_at", major=21, path="C:/jdk/bin/java.exe")
    assert page.java_status.property("tone") == "ok"
    page._pick_java = lambda _parent: "C:/jdk-17/bin/java.exe"  # type: ignore[method-assign]
    page.choose_java()
    assert page.java_label.text() == MESSAGES.text("settings.java.custom", path="C:/jdk-17/bin/java.exe")
    assert page.java_status.text() == MESSAGES.text("settings.java.found", major=21)
    page.use_automatic_java()
    assert page.java_label.text() == MESSAGES.text("settings.java.automatic_hint")
    assert page.theme_combo.accessibleName() == MESSAGES.text("settings.theme.label")
    assert page.footer.objectName() == "pageFooter"  # Save stays in view on the long page


# --- MCServer 0.9.1 is gone from the interface ------------------------------------------------


@pytest.mark.parametrize("language", ["en", "uk"])
def test_no_interface_text_mentions_mcserver_0_9_1(language: str) -> None:
    catalog = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
    assert [key for key, text in catalog.items() if "0.9.1" in text or key.startswith(("legacy.", "menu."))] == []


def test_the_window_has_no_legacy_import_controls(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M2Setup(qtbot, tmp_path, SURVIVAL)
    window = setup.window
    for name in ("import_legacy_action", "offer_legacy_import", "first_run_action", "java_status_label"):
        assert not hasattr(window, name), name


@pytest.mark.parametrize("language", ["en", "uk"])
def test_create_dialog_content_never_overflows_its_card(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    import test_m2_gui

    monkeypatch.setattr(test_m2_gui, "MESSAGES", messages_for(language))
    setup = M2Setup(qtbot, tmp_path)
    window = setup.window
    # Any catalog makes the download button show; closing the window asks whether it is busy.
    window.jar_catalog_controller = SimpleNamespace(state=SimpleNamespace(busy=False))  # type: ignore[assignment]
    window.resize(window.minimumWidth(), window.minimumHeight())
    window.show()
    window.open_create_dialog()
    dialog = window.create_dialog
    assert dialog is not None and not dialog.download_button.isHidden()
    dialog._use_jar("C:/Downloads/paper-1.21.4-232-with-a-rather-long-file-name.jar")  # type: ignore[attr-defined]
    qtbot.wait(20)
    card = dialog.parentWidget()
    while card is not None and card.objectName() != "modalCard":
        card = card.parentWidget()
    assert card is not None
    assert dialog.minimumSizeHint().width() <= card.width()  # nothing is pushed past the right edge
    assert dialog.width() <= card.width()


# --- logo -----------------------------------------------------------------------------------


def test_the_logo_is_the_window_icon_at_every_common_size(qtbot: QtBot) -> None:
    from mcserver.presentation import icons

    app_icon = icons.app_icon()
    assert sorted(size.width() for size in app_icon.availableSizes()) == sorted(icons.APP_ICON_SIZES)
    logo = icons.logo_pixmap(32, 1.0).toImage()
    assert logo.pixelColor(16, 3).green() > 180  # the green square, drawn and not blank
    assert logo.pixelColor(0, 0).alpha() == 0  # rounded corners stay transparent


def test_the_welcome_page_shows_the_logo(qtbot: QtBot, tmp_path: Path) -> None:
    setup = M3Setup(qtbot, tmp_path)
    logo = setup.window.dashboard_view.welcome_page.findChild(QWidget, "welcomeLogo")
    assert logo is not None and not logo.pixmap().isNull()


# --- about (M5) -----------------------------------------------------------------------------


def test_about_shows_the_version_and_project_page(qtbot: QtBot, tmp_path: Path) -> None:
    import mcserver
    from mcserver.presentation.dialogs.about_dialog import AboutDialog

    setup = M2Setup(qtbot, tmp_path, SURVIVAL)
    window = setup.window
    window.open_settings_dialog()
    assert window.settings_dialog is not None
    window.settings_dialog.about_button.click()
    about = window.page_host.current_page
    assert isinstance(about, AboutDialog)
    assert about.version_label.text() == MESSAGES.text("about.version", version=mcserver.__version__)
    assert about.homepage_button.toolTip() == mcserver.HOMEPAGE
    assert mcserver.COPYRIGHT in about.license_label.text()


def test_a_long_path_in_a_banner_wraps_instead_of_widening_the_dialog(qtbot: QtBot) -> None:
    from mcserver.presentation.views.widgets import Banner

    banner = Banner()
    qtbot.addWidget(banner)
    path = r"C:\Program Files\Common Files\Oracle\Java\javapath_target_419678718\java.exe"
    banner.show_message(f"Found Java 25: {path}", "success")
    assert banner.minimumSizeHint().width() < 320
    assert banner.text.text().replace("\u200b", "") == f"Found Java 25: {path}"  # copying gives the real path
