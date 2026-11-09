"""Offscreen Qt tests for the dashboard: controls, status, console and closing the window."""

from pathlib import Path
from threading import Event

from fakes import FakeRunnerFactory, InMemoryRepository, coordinator, services_for
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from mcserver.application.ports import OutputStream
from mcserver.application.server_output import ServerOutputBuffer
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.main_window import MainWindow

SURVIVAL = ServerConfiguration("survival", "survival", "paper.jar", 4096)
CREATIVE = ServerConfiguration("creative", "creative", "fabric.jar", 2048)
MESSAGES = messages_for()


class Setup:
    def __init__(self, qtbot: QtBot, root: Path, *, java: bool = True, confirm: bool = True) -> None:
        self.factory = FakeRunnerFactory()
        self.coordinator = coordinator(self.factory)
        self.output = ServerOutputBuffer()
        self.closes: list[str] = []
        self.confirm_calls: list[str] = []
        self.opened: list[Path] = []
        self.services = services_for(
            InMemoryRepository(SURVIVAL, CREATIVE),
            root=root,
            java=java,
            closes=self.closes,
            server_coordinator=self.coordinator,
            output=self.output,
        )
        self.window = MainWindow(
            self.services,
            MESSAGES,
            confirm_exit=lambda server_id: self.confirm_calls.append(server_id) or confirm,
            open_folder=lambda path: self.opened.append(path) or False,
        )
        qtbot.addWidget(self.window)
        self.window.show()

    def select(self, row: int) -> None:
        self.window.server_list_view.list_widget.setCurrentRow(row)

    @property
    def dashboard(self):  # type: ignore[no-untyped-def]
        return self.window.dashboard_view


def wait_until_running(qtbot: QtBot, setup: Setup) -> None:
    """Wait until the start has finished in the GUI, not only in the coordinator."""
    qtbot.waitUntil(
        lambda: setup.coordinator.active_server_id == "survival" and not setup.window.dashboard_controller.busy
    )


def test_closing_during_an_operation_asks_to_wait(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    gate = Event()
    setup.factory.runner.start_gate = gate
    setup.select(0)
    qtbot.mouseClick(setup.dashboard.start_button, Qt.MouseButton.LeftButton)

    setup.window.close()

    assert setup.window.isVisible()
    assert setup.window.statusBar().currentMessage() == MESSAGES.text("exit.wait_for_operation")
    assert setup.confirm_calls == []
    gate.set()
    wait_until_running(qtbot, setup)


def test_dashboard_shows_server_card_and_enabled_start(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)

    setup.select(0)

    dashboard = setup.dashboard
    assert dashboard.title_label.text() == "survival"
    memory = MESSAGES.text("server_details.memory_value", memory_mb=4096)
    assert dashboard.subtitle_label.text() == MESSAGES.text("dashboard.subtitle", jar_file="paper.jar", memory=memory)
    assert dashboard.status_pill.property("status") == "stopped"
    assert dashboard.start_button.isEnabled() and not dashboard.stop_button.isEnabled()
    assert dashboard.start_button.text() == MESSAGES.text("dashboard.start")


def test_start_and_stop_through_buttons_update_status_list_and_console(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select(0)
    dashboard = setup.dashboard

    qtbot.mouseClick(dashboard.start_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: dashboard.status_pill.property("status") == "running")
    assert dashboard.stop_button.isEnabled() and not dashboard.start_button.isEnabled()
    assert setup.factory.runner.started == ["survival"]
    qtbot.waitUntil(lambda: "Running" in setup.window.server_list_view.list_widget.item(0).text())

    setup.output.publish("survival", OutputStream.STDOUT, 'Done (2.0s)! For help, type "help"')
    qtbot.waitUntil(lambda: "Done (2.0s)!" in dashboard.console.plain_text())

    qtbot.mouseClick(dashboard.stop_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: dashboard.status_pill.property("status") == "stopped")
    assert dashboard.start_button.isEnabled()
    assert dashboard.banner.isHidden()


def test_switching_server_while_one_runs_blocks_second_start(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select(0)
    qtbot.mouseClick(setup.dashboard.start_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: setup.dashboard.status_pill.property("status") == "running")

    setup.select(1)

    dashboard = setup.dashboard
    qtbot.waitUntil(lambda: dashboard.title_label.text() == "creative")
    qtbot.waitUntil(
        lambda: dashboard.hint_label.text() == MESSAGES.text("dashboard.hint.other_running", server_id="survival")
    )
    assert not dashboard.start_button.isEnabled() and not dashboard.stop_button.isEnabled()


def test_console_follows_selected_server(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.output.publish("survival", OutputStream.STDOUT, "survival history")
    setup.output.publish("creative", OutputStream.STDERR, "creative history")

    setup.select(0)
    qtbot.waitUntil(lambda: setup.dashboard.console.plain_text() == "survival history")
    setup.select(1)
    qtbot.waitUntil(lambda: setup.dashboard.console.plain_text() == "creative history")

    qtbot.mouseClick(setup.dashboard.console.clear_button, Qt.MouseButton.LeftButton)
    assert setup.dashboard.console.plain_text() == ""
    assert len(setup.output.snapshot()) == 2


def test_start_failure_shows_error_banner_with_details(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.factory.runner.start_error = FileNotFoundError("java.exe")
    setup.select(0)

    qtbot.mouseClick(setup.dashboard.start_button, Qt.MouseButton.LeftButton)

    banner = setup.dashboard.banner
    qtbot.waitUntil(lambda: banner.isVisible())
    assert banner.text() == MESSAGES.text("errors.start_failed", server_id="survival")
    assert "FileNotFoundError: java.exe" in banner.toolTip()
    assert banner.property("tone") == "error"
    assert setup.dashboard.start_button.isEnabled()


def test_unexpected_stop_shows_notice(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select(0)
    qtbot.mouseClick(setup.dashboard.start_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: setup.coordinator.active_server_id == "survival")

    setup.factory.runner.exit(1)

    banner = setup.dashboard.banner
    qtbot.waitUntil(lambda: banner.isVisible())
    assert banner.text() == MESSAGES.text("dashboard.notice.stopped_unexpectedly", server_id="survival")
    assert banner.property("tone") == "notice"


def test_java_missing_disables_controls_and_explains(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, java=False)

    setup.select(0)

    dashboard = setup.dashboard
    assert not dashboard.start_button.isEnabled() and not dashboard.stop_button.isEnabled()
    assert dashboard.hint_label.text() == MESSAGES.text("dashboard.hint.java_missing")
    assert dashboard.console.pages.currentWidget() is dashboard.console.unavailable_label


def test_open_folder_failure_is_reported_in_status_bar(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select(0)

    qtbot.mouseClick(setup.dashboard.open_folder_button, Qt.MouseButton.LeftButton)

    assert setup.opened == [tmp_path / "survival"]
    expected = MESSAGES.text("dashboard.open_folder_failed", path=str(tmp_path / "survival"))
    assert setup.window.statusBar().currentMessage() == expected


def test_closing_with_running_server_asks_then_stops_and_closes(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select(0)
    qtbot.mouseClick(setup.dashboard.start_button, Qt.MouseButton.LeftButton)
    wait_until_running(qtbot, setup)

    setup.window.close()

    assert setup.confirm_calls == ["survival"]
    qtbot.waitUntil(lambda: not setup.window.isVisible())
    assert setup.factory.runner.stopped != []
    assert setup.coordinator.active_server_id is None
    assert setup.closes == []  # the window never closes backend services
    assert len(setup.output._subscriptions) == 0  # type: ignore[attr-defined]


def test_cancelling_exit_keeps_server_running(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, confirm=False)
    setup.select(0)
    qtbot.mouseClick(setup.dashboard.start_button, Qt.MouseButton.LeftButton)
    wait_until_running(qtbot, setup)

    setup.window.close()

    assert setup.window.isVisible()
    assert setup.coordinator.active_server_id == "survival"
    setup.factory.runner.exit(0)  # let fixture teardown close the window
    qtbot.waitUntil(lambda: setup.coordinator.active_server_id is None)


def test_closing_idle_window_releases_poller_and_subscription(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select(0)
    assert setup.window.poller is not None and setup.window.poller.active

    setup.window.close()

    assert not setup.window.isVisible()
    assert not setup.window.poller.active
    assert len(setup.output._subscriptions) == 0  # type: ignore[attr-defined]
    assert setup.confirm_calls == []
