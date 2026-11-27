"""CPU and memory history charts in the resources card (M4-GUI-06)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QColor
from pytestqt.qtbot import QtBot
from test_m3_gui import Setup

from mcserver.application.server_metrics import ServerMetricsSnapshot
from mcserver.domain.lifecycle import ServerState
from mcserver.presentation import theme
from mcserver.presentation.app import WindowHost
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.metrics_history import HISTORY_CAPACITY, MetricsHistory
from mcserver.presentation.views.charts import Sparkline

MESSAGES = messages_for()


def snapshot(server_id: str = "survival", cpu: float = 10.0, memory: float = 900.0, uptime: int = 60):
    return ServerMetricsSnapshot(server_id, ServerState.RUNNING, cpu, memory, 2048, uptime)


@pytest.fixture(autouse=True)
def dark_theme() -> Iterator[None]:
    theme.apply("dark")
    yield
    theme.apply("dark")


# --- history ----------------------------------------------------------------------------------


def test_history_keeps_the_newest_samples_per_server() -> None:
    history = MetricsHistory(capacity=3)
    for second in range(5):
        history.add(snapshot(cpu=second, uptime=60 + second))
    history.add(snapshot("creative", cpu=99, uptime=10))

    assert [point.cpu_percent for point in history.points("survival")] == [2, 3, 4]
    assert [point.cpu_percent for point in history.points("creative")] == [99]
    assert history.points(None) == () and history.points("unknown") == ()


def test_a_restart_starts_a_new_series_and_forget_drops_it() -> None:
    history = MetricsHistory()
    history.add(snapshot(uptime=500))
    history.add(snapshot(uptime=502))
    history.add(snapshot(uptime=2))  # started again
    assert [point.uptime_seconds for point in history.points("survival")] == [2]
    history.forget("survival")
    assert history.points("survival") == ()


def test_the_same_moment_sampled_twice_is_one_point() -> None:
    history = MetricsHistory()
    history.add(snapshot(cpu=10, uptime=60))
    history.add(snapshot(cpu=12, uptime=60))
    assert [point.cpu_percent for point in history.points("survival")] == [12]


def test_ten_minutes_of_samples_are_kept_by_default() -> None:
    assert HISTORY_CAPACITY * 2 == 600


# --- the chart widget ---------------------------------------------------------------------------


def test_chart_draws_newest_on_the_right_and_scales_to_the_maximum(qtbot: QtBot) -> None:
    chart = Sparkline("ACCENT", capacity=10)
    qtbot.addWidget(chart)
    chart.resize(201, 40)
    chart.set_series([0, 50, 100], 100, active=True, description="cpu")

    points = chart.points()
    assert len(points) == 3
    assert points[-1].x() == pytest.approx(200, abs=0.5)  # the newest sample sits at the right edge
    assert points[0].y() > points[1].y() > points[2].y()  # higher values are drawn higher
    assert points[2].y() == pytest.approx(2, abs=0.5)  # 100 of 100 reaches the top

    chart.set_series([10], 100, active=True, description="one sample")
    assert chart.points() == []  # a single sample is not a line yet


def test_values_above_the_maximum_raise_the_scale(qtbot: QtBot) -> None:
    chart = Sparkline("ACCENT", capacity=10)
    qtbot.addWidget(chart)
    chart.set_series([50, 250], 100, active=True, description="cpu on several cores")
    assert chart.maximum == 250


def test_chart_colour_follows_the_theme_and_dims_when_stopped(qtbot: QtBot) -> None:
    chart = Sparkline("INFO", capacity=10)
    qtbot.addWidget(chart)
    chart.resize(120, 40)
    chart.set_series([10, 40, 20, 60], 100, active=True, description="memory")
    assert chart.color().name() == theme.DARK["INFO"]

    theme.apply("light")
    assert chart.color().name() == theme.LIGHT["INFO"]
    image = chart.grab().toImage()
    painted = {image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())}
    assert QColor(theme.LIGHT["INFO"]).name() in painted

    chart.set_series([10, 40], 100, active=False, description="stopped")
    assert chart.color().name() == theme.LIGHT["TEXT_MUTED"]


# --- in the window --------------------------------------------------------------------------


def test_the_running_server_builds_history_while_another_is_selected(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("creative")
    for second in range(3):
        setup.metrics.snapshot = snapshot("survival", cpu=20 + second, uptime=60 + second * 2)
        setup.window.sample_metrics()

    history = setup.window._services.metrics_history  # type: ignore[attr-defined]
    assert [point.cpu_percent for point in history.points("survival")] == [20, 21, 22]
    assert setup.window.dashboard_view.charts["cpu"].values == ()  # creative has no history

    setup.select("survival")
    setup.window.sample_metrics()
    chart = setup.window.dashboard_view.charts["cpu"]
    assert chart.values == (20, 21, 22) and chart.active  # re-sampling the same moment adds no point
    assert chart.accessibleDescription() == MESSAGES.text("metrics.history_cpu", minutes=10, low="20", high="22")
    memory = setup.window.dashboard_view.charts["memory"]
    assert memory.maximum == 2048  # memory is drawn against what the server may use


def test_a_stopped_server_keeps_its_history_dimmed(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    for second in range(3):
        setup.metrics.snapshot = snapshot(cpu=30, uptime=60 + second * 2)
        setup.window.sample_metrics()
    setup.metrics.snapshot = None  # stopped (or crashed)
    setup.window.sample_metrics()

    chart = setup.window.dashboard_view.charts["cpu"]
    assert len(chart.values) == 3 and not chart.active


def test_empty_history_is_described_for_screen_readers(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    setup.window.sample_metrics()
    for name in ("cpu", "memory"):
        chart = setup.window.dashboard_view.charts[name]
        assert chart.accessibleName() == MESSAGES.text(f"metrics.{name}")
        assert chart.accessibleDescription() == MESSAGES.text("metrics.history_empty")


def test_history_survives_a_window_rebuild(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    services = setup.window._services  # type: ignore[attr-defined]
    for second in range(4):
        setup.metrics.snapshot = snapshot(cpu=40, uptime=60 + second * 2)
        setup.window.sample_metrics()
    host = WindowHost(services, MESSAGES)
    qtbot.addWidget(host.window)
    host.window.server_list_controller.select("survival")

    new = host.switch_language("uk")
    qtbot.addWidget(new)
    new.server_list_controller.select("survival")
    new.sample_metrics()

    assert len(new.dashboard_view.charts["cpu"].values) == 4
