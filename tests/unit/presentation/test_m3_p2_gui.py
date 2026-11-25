"""Offscreen Qt tests for M3 P2: restart, auto-restart, console history/filter/save, tools and activity tiles."""

from __future__ import annotations

from pathlib import Path

from fakes import FakeRunnerFactory, InMemoryRepository, coordinator, services_for
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from pytestqt.qtbot import QtBot

from mcserver.application.auto_restart import AutoRestartPolicy
from mcserver.application.ports import OutputStream
from mcserver.application.server_activity import ServerActivity
from mcserver.application.server_address import ServerAddressLookup
from mcserver.application.server_metrics import ServerMetricsSnapshot
from mcserver.application.server_output import ServerOutputBuffer
from mcserver.application.server_properties import ServerPropertiesService
from mcserver.domain.lifecycle import ServerState
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.server_properties_file import FileServerPropertiesStore
from mcserver.presentation.controllers.console import ConsoleLine, LineLevel, line_level
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.main_window import MainWindow

MESSAGES = messages_for()
SURVIVAL = ServerConfiguration("survival", "survival", "paper.jar", 2048)
CREATIVE = ServerConfiguration("creative", "creative", "paper.jar", 1024)


class Metrics:
    def __init__(self) -> None:
        self.snapshot: ServerMetricsSnapshot | None = None

    def sample(self) -> ServerMetricsSnapshot | None:
        return self.snapshot


class Setup:
    def __init__(
        self, qtbot: QtBot, root: Path, *, auto_restart: bool = False, lan: str | None = "192.168.1.5"
    ) -> None:
        (root / "survival").mkdir(parents=True)
        (root / "survival" / "server.properties").write_text("server-port=25570\nmax-players=12\n", encoding="utf-8")
        self.factory = FakeRunnerFactory()
        self.coordinator = coordinator(self.factory)
        self.output = ServerOutputBuffer()
        self.repository = InMemoryRepository(SURVIVAL, CREATIVE)
        self.opened: list[Path] = []
        self.saved_to = root / "saved.log"
        self.services = services_for(
            self.repository, root=root, server_coordinator=self.coordinator, output=self.output
        )
        properties = ServerPropertiesService(FileServerPropertiesStore(root, self.repository))
        self.activity = ServerActivity(max_players=lambda _server_id: 12)
        self.output.subscribe(self.activity.on_line, replay=False)
        self.metrics = Metrics()
        self.policy = AutoRestartPolicy(lambda: auto_restart, max_restarts=2)
        self.services.properties = properties
        self.services.activity = self.activity
        self.services.metrics = self.metrics  # type: ignore[assignment]
        self.services.auto_restart = self.policy
        self.services.address = ServerAddressLookup(properties, lambda: lan)
        self.window = MainWindow(
            self.services,
            MESSAGES,
            confirm_exit=lambda _server_id: True,
            open_folder=lambda path: self.opened.append(path) or True,
            notify_unclean=lambda _incident: None,
            offer_legacy_import=lambda _count: False,
            choose_log_path=lambda _server_id: str(self.saved_to),
            auto_restart_delay_ms=20,
        )
        qtbot.addWidget(self.window)
        self.window.show()
        self.qtbot = qtbot

    def select(self, server_id: str) -> None:
        self.window.server_list_controller.select(server_id)

    @property
    def dashboard(self):  # type: ignore[no-untyped-def]
        return self.window.dashboard_view

    def start(self) -> None:
        self.select("survival")
        self.qtbot.mouseClick(self.dashboard.start_button, Qt.MouseButton.LeftButton)
        self.wait_running()

    def wait_running(self) -> None:
        self.qtbot.waitUntil(
            lambda: self.coordinator.state is ServerState.RUNNING and not self.window.dashboard_controller.busy
        )
        self.qtbot.waitUntil(lambda: self.window.dashboard_controller.state.can_restart)

    def emit(self, text: str, stream: OutputStream = OutputStream.STDOUT) -> None:
        self.output.publish("survival", stream, text)

    def stop_for_teardown(self) -> None:
        self.factory.runner.exit(0)


# --- restart (M3-BE-05) ---------------------------------------------------------------------------


def test_restart_stops_gracefully_and_starts_again(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    assert not setup.dashboard.restart_button.isVisible()
    setup.start()
    assert setup.dashboard.restart_button.isVisible() and setup.dashboard.restart_button.isEnabled()

    qtbot.mouseClick(setup.dashboard.restart_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: len(setup.factory.runner.started) == 2, timeout=5000)
    setup.wait_running()
    assert setup.factory.runner.stopped and setup.factory.runner.killed == 0
    assert setup.window.dashboard_controller.state.notice is None
    assert setup.window.dashboard_controller.state.error is None
    setup.stop_for_teardown()


def test_crash_is_not_restarted_when_auto_restart_is_off(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.start()
    setup.factory.runner.exit(1)
    qtbot.waitUntil(lambda: setup.window.dashboard_controller.state.error is not None)
    qtbot.wait(100)
    assert setup.factory.runner.started == ["survival"]


def test_crash_is_restarted_automatically_up_to_the_limit(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, auto_restart=True)
    setup.start()
    for attempt in (1, 2):
        setup.factory.runner.exit(1)
        qtbot.waitUntil(lambda attempt=attempt: len(setup.factory.runner.started) == attempt + 1, timeout=5000)
        setup.wait_running()
        notice = setup.window.dashboard_controller.state.notice
        assert notice is not None and notice.key == "dashboard.notice.auto_restarted"
        assert notice.params["attempt"] == attempt

    setup.factory.runner.exit(1)  # third crash: the limit of 2 is reached
    qtbot.waitUntil(lambda: setup.window.dashboard_controller.state.hint is not None)
    hint = setup.window.dashboard_controller.state.hint
    assert hint is not None and hint.key == "dashboard.hint.auto_restart_gave_up"
    qtbot.wait(100)
    assert len(setup.factory.runner.started) == 3
    assert setup.dashboard.hint_label.text() == MESSAGES.text("dashboard.hint.auto_restart_gave_up", limit=2)


def test_user_start_cancels_a_pending_auto_restart(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, auto_restart=True)
    setup.window.dashboard_controller._auto_restart_delay_ms = 60_000  # type: ignore[attr-defined]
    setup.start()
    setup.factory.runner.exit(1)
    qtbot.waitUntil(lambda: setup.window.dashboard_controller.state.hint is not None)
    assert setup.window.dashboard_controller.state.hint.key == "dashboard.hint.auto_restarting"  # type: ignore[union-attr]
    qtbot.mouseClick(setup.dashboard.start_button, Qt.MouseButton.LeftButton)
    setup.wait_running()
    assert setup.window.dashboard_controller.state.hint is None
    setup.stop_for_teardown()


# --- console (M3-GUI-01) -------------------------------------------------------------------------


def test_line_levels() -> None:
    assert line_level("[12:00:00] [Server thread/WARN]: Can't keep up!") is LineLevel.WARNING
    assert line_level("[12:00:00 ERROR]: Could not load plugin") is LineLevel.ERROR
    assert line_level("[12:00:00 INFO]: Done") is LineLevel.INFO
    assert line_level("Exception in thread main", is_error=True) is LineLevel.ERROR
    assert ConsoleLine(1, False, "[x/WARN]: y", is_command=True).level is LineLevel.INFO


def test_console_filter_history_and_save(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.start()
    console = setup.dashboard.console
    setup.emit("[12:00:01] [Server thread/INFO]: hello world")
    setup.emit("[12:00:02] [Server thread/WARN]: Can't keep up!")
    setup.emit("Exception in thread", OutputStream.STDERR)
    qtbot.waitUntil(lambda: "Exception in thread" in console.plain_text())

    console.filter_combo.setCurrentIndex(1)  # warnings and errors
    text = console.plain_text()
    assert "Can't keep up!" in text and "Exception in thread" in text and "hello world" not in text
    console.filter_combo.setCurrentIndex(0)
    assert "hello world" in console.plain_text()

    for command in ("say one", "say two"):
        console.input.setText(command)
        qtbot.keyClick(console.input, Qt.Key.Key_Return)
    console.input.setText("draft")
    qtbot.keyClick(console.input, Qt.Key.Key_Up)
    assert console.input.text() == "say two"
    qtbot.keyClick(console.input, Qt.Key.Key_Up)
    qtbot.keyClick(console.input, Qt.Key.Key_Up)
    assert console.input.text() == "say one"
    qtbot.keyClick(console.input, Qt.Key.Key_Down)
    qtbot.keyClick(console.input, Qt.Key.Key_Down)
    assert console.input.text() == "draft"

    console.filter_combo.setCurrentIndex(1)  # saving ignores the filter
    qtbot.mouseClick(console.save_button, Qt.MouseButton.LeftButton)
    saved = setup.saved_to.read_text(encoding="utf-8")
    assert "hello world" in saved and "Can't keep up!" in saved
    assert MESSAGES.text("console.saved", path=str(setup.saved_to)) in setup.window.notification_texts()
    setup.stop_for_teardown()


# --- tools (M3-GUI-05) and activity tiles (M3-GUI-08) --------------------------------------------


def test_address_row_logs_button_and_copy(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    assert setup.dashboard.address_value.text() == "192.168.1.5:25570"
    qtbot.mouseClick(setup.dashboard.copy_address_button, Qt.MouseButton.LeftButton)
    assert QGuiApplication.clipboard().text() == "192.168.1.5:25570"

    qtbot.mouseClick(setup.dashboard.open_logs_button, Qt.MouseButton.LeftButton)
    assert setup.opened == []  # no logs folder yet
    assert MESSAGES.text("dashboard.no_logs") in setup.window.notification_texts()
    (tmp_path / "survival" / "logs").mkdir()
    qtbot.mouseClick(setup.dashboard.open_logs_button, Qt.MouseButton.LeftButton)
    assert setup.opened == [tmp_path / "survival" / "logs"]

    setup.select("creative")
    assert setup.dashboard.address_value.text() == "192.168.1.5"


def test_address_without_network(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, lan=None)
    setup.select("survival")
    assert setup.dashboard.address_value.text() == MESSAGES.text("dashboard.address_unknown")
    assert not setup.dashboard.copy_address_button.isEnabled()


def test_players_and_tps_tiles(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.start()
    values = setup.dashboard.metric_values
    setup.emit("[12:00:01] [Server thread/INFO]: Steve joined the game")
    setup.emit("[12:00:02 INFO]: TPS from last 1m, 5m, 15m: 19.5, 20.0, 20.0")
    assert setup.output.flush(5)
    setup.metrics.snapshot = ServerMetricsSnapshot("survival", ServerState.RUNNING, 5.0, 900.0, 2048, 10)
    setup.window.sample_metrics()
    assert values["players"].text() == "1 / 12"
    assert values["players"].toolTip() == "Steve"
    assert values["tps"].text() == "19.5"

    setup.metrics.snapshot = None
    setup.window.sample_metrics()
    assert values["players"].text() == MESSAGES.text("metrics.idle")
    setup.stop_for_teardown()


def test_settings_dialog_saves_auto_restart(qtbot: QtBot, tmp_path: Path) -> None:
    from test_m2_gui import Setup as M2Setup

    m2 = M2Setup(qtbot, tmp_path)
    window, settings = m2.window, m2.settings
    window.open_settings_dialog()
    dialog = window.settings_dialog
    assert dialog is not None and not dialog.auto_restart_check.isChecked()
    dialog.auto_restart_check.setChecked(True)
    dialog.save()
    assert settings.current.auto_restart is True
