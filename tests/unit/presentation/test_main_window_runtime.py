"""Offscreen Qt tests for M1 window flows: Kill, EULA prompt, Java guidance, incidents, exit after a stop timeout."""

from __future__ import annotations

from pathlib import Path

from fakes import (
    FakeRunner,
    FakeRunnerFactory,
    InMemoryRepository,
    MemoryFilesystem,
    MemoryMarkers,
    coordinator,
    services_for,
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from mcserver.application.errors import EulaNotAccepted, JavaNotFound, JavaVersionTooOld
from mcserver.application.java_setup import JavaSetup
from mcserver.application.ports import JavaInstallation, StartOptions
from mcserver.application.server_health import ServerHealth, UncleanShutdown
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.presentation.dialogs.error_details_dialog import ErrorDetailsDialog
from mcserver.presentation.dialogs.java_setup_dialog import JavaChoice
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.main_window import MainWindow, StopTimeoutChoice

SURVIVAL = ServerConfiguration("survival", "survival", "paper.jar", 4096)
MESSAGES = messages_for()


class Provider:
    configured_executable: str | None = None

    def __init__(self, major: int | None = 21) -> None:
        self.major = major

    def find(self, minimum_major: int | None = None) -> JavaInstallation:
        if self.major is None:
            raise JavaNotFound(minimum_major)
        return JavaInstallation("C:/jdk/bin/java.exe", self.major, "installed")

    def configure(self, executable: str | None) -> JavaInstallation | None:
        return None


class Setup:
    def __init__(
        self,
        qtbot: QtBot,
        root: Path,
        *,
        runner: FakeRunner | None = None,
        markers: MemoryMarkers | None = None,
        java_major: int | None = 21,
        kill_answer: bool = True,
        eula_answer: bool = True,
        java_choice: JavaChoice = JavaChoice.CANCELLED,
        timeout_choice: StopTimeoutChoice = StopTimeoutChoice.CANCEL,
    ) -> None:
        self.factory = FakeRunnerFactory(runner or FakeRunner())
        self.coordinator = coordinator(self.factory)
        self.filesystem = MemoryFilesystem("survival")
        self.markers = markers or MemoryMarkers()
        self.provider = Provider(java_major)
        self.asked: dict[str, list[object]] = {"kill": [], "eula": [], "java": [], "unclean": [], "timeout": []}
        self.java_choice = java_choice
        self.timeout_choice = timeout_choice
        self.before_timeout_answer = lambda: None
        services = services_for(
            InMemoryRepository(SURVIVAL),
            root=root,
            server_coordinator=self.coordinator,
            filesystem=self.filesystem,
            java_setup=JavaSetup(self.provider),
            health=ServerHealth(self.markers),
        )

        def answer_eula(server_id: str) -> bool:
            self.asked["eula"].append(server_id)
            if eula_answer:
                self.factory.preflight_error = None
            return eula_answer

        def answer_java(problem: object) -> JavaChoice:
            self.asked["java"].append(problem)
            self.factory.preflight_error = None
            return self.java_choice

        def answer_timeout(server_id: str, timeout: float) -> StopTimeoutChoice:
            self.asked["timeout"].append((server_id, timeout))
            self.before_timeout_answer()
            return self.timeout_choice

        self.window = MainWindow(
            services,
            MESSAGES,
            confirm_exit=lambda _server_id: True,
            confirm_kill=lambda server_id: self.asked["kill"].append(server_id) or kill_answer,
            confirm_eula=answer_eula,
            handle_java_problem=answer_java,
            notify_unclean=lambda incident: self.asked["unclean"].append(incident),
            ask_after_stop_timeout=answer_timeout,
        )
        qtbot.addWidget(self.window)
        self.window.show()
        self.window.server_list_view.list_widget.setCurrentRow(0)
        self.qtbot = qtbot

    @property
    def runner(self) -> FakeRunner:
        return self.factory.runner

    @property
    def dashboard(self):  # type: ignore[no-untyped-def]
        return self.window.dashboard_view

    def start_and_wait_running(self) -> None:
        self.qtbot.mouseClick(self.dashboard.start_button, Qt.MouseButton.LeftButton)
        self.qtbot.waitUntil(
            lambda: (
                self.dashboard.status_pill.property("status") == "running" and not self.window.dashboard_controller.busy
            )
        )


def test_stop_timeout_shows_kill_and_kill_needs_confirmation(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, runner=FakeRunner(stop_exits=False), kill_answer=False)
    setup.start_and_wait_running()
    assert setup.dashboard.kill_button.isHidden()

    qtbot.mouseClick(setup.dashboard.stop_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: setup.dashboard.kill_button.isVisible() and setup.dashboard.kill_button.isEnabled())
    assert setup.dashboard.status_pill.property("status") == "stopping"
    assert setup.dashboard.banner.text() == MESSAGES.text("errors.stop_timed_out", server_id="survival", timeout="90")
    assert setup.runner.killed == 0

    qtbot.mouseClick(setup.dashboard.kill_button, Qt.MouseButton.LeftButton)
    assert setup.asked["kill"] == ["survival"] and setup.runner.killed == 0  # declined: nothing killed

    setup.window._confirm_kill = lambda _server_id: True  # type: ignore[method-assign]
    qtbot.mouseClick(setup.dashboard.kill_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: setup.dashboard.status_pill.property("status") == "stopped")
    assert setup.runner.killed == 1


def test_console_input_sends_commands_only_while_running(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    console = setup.dashboard.console
    assert not console.input.isEnabled()

    setup.start_and_wait_running()
    assert console.input.isEnabled()
    qtbot.keyClicks(console.input, "say hi")
    qtbot.keyClick(console.input, Qt.Key.Key_Return)

    qtbot.waitUntil(lambda: setup.runner.commands == ["say hi"])
    assert console.input.text() == ""


def test_missing_eula_is_asked_then_accepted_and_the_server_starts(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.factory.preflight_error = EulaNotAccepted("survival")

    qtbot.mouseClick(setup.dashboard.start_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: setup.dashboard.status_pill.property("status") == "running")
    assert setup.asked["eula"] == ["survival"]
    assert "eula:survival" in setup.filesystem.calls
    assert setup.dashboard.banner.isHidden()


def test_declined_eula_starts_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, eula_answer=False)
    setup.factory.preflight_error = EulaNotAccepted("survival")

    qtbot.mouseClick(setup.dashboard.start_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: setup.asked["eula"] == ["survival"] and not setup.window.dashboard_controller.busy)
    assert setup.runner.started == []
    assert "eula:survival" not in setup.filesystem.calls


def test_old_java_start_anyway_passes_the_override(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, java_choice=JavaChoice.START_ANYWAY)
    setup.factory.preflight_error = JavaVersionTooOld("survival", 25, 21, "C:/jdk/bin/java.exe")

    qtbot.mouseClick(setup.dashboard.start_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: setup.dashboard.status_pill.property("status") == "running")
    assert isinstance(setup.asked["java"][0], JavaVersionTooOld)
    assert setup.factory.options[-1] == StartOptions(allow_outdated_java=True)


def test_missing_java_retry_starts_normally_and_updates_the_status_bar(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, java_choice=JavaChoice.RETRY)
    setup.factory.preflight_error = JavaNotFound(21)

    qtbot.mouseClick(setup.dashboard.start_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: setup.dashboard.status_pill.property("status") == "running")
    assert setup.factory.options[-1] == StartOptions()
    assert setup.window.java_status_label.text() == MESSAGES.text("status.java_ready", major=21)


def test_check_java_reports_missing_java(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, java_major=None)

    setup.window.java_check_button.click()

    assert setup.window.java_status_label.text() == MESSAGES.text("status.java_missing")


def test_unclean_shutdown_is_reported_once_without_recovery_actions(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, markers=MemoryMarkers("survival"))

    qtbot.waitUntil(lambda: len(setup.asked["unclean"]) == 1)
    incident = setup.asked["unclean"][0]
    assert isinstance(incident, UncleanShutdown) and incident.server_id == "survival"
    assert setup.markers.markers == {}  # acknowledged: not shown again
    setup.window.report_unclean_shutdowns()
    assert len(setup.asked["unclean"]) == 1


def test_unclean_notice_text_names_server_and_possible_loss() -> None:
    text = MESSAGES.text("unclean.text", server_id="survival", started_at="2026-11-15T09:00:00+00:00")
    assert "survival" in text and "lost" in text and "backup" not in text.lower()


def test_exit_after_stop_timeout_can_be_cancelled(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, runner=FakeRunner(stop_exits=False), timeout_choice=StopTimeoutChoice.CANCEL)
    setup.start_and_wait_running()

    setup.window.close()

    qtbot.waitUntil(lambda: setup.asked["timeout"] == [("survival", 90.0)])
    qtbot.waitUntil(lambda: not setup.window.dashboard_controller.busy)
    assert setup.window.isVisible()
    assert setup.coordinator.active_server_id == "survival"
    assert setup.runner.killed == 0


def test_exit_after_stop_timeout_can_kill_and_close(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, runner=FakeRunner(stop_exits=False), timeout_choice=StopTimeoutChoice.KILL)
    setup.start_and_wait_running()

    setup.window.close()

    qtbot.waitUntil(lambda: not setup.window.isVisible())
    assert setup.runner.killed == 1


def test_exit_after_stop_timeout_can_keep_waiting(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, runner=FakeRunner(stop_exits=False), timeout_choice=StopTimeoutChoice.KEEP_WAITING)

    def finish_saving() -> None:
        setup.runner.stop_exits = True

    setup.before_timeout_answer = finish_saving
    setup.start_and_wait_running()

    setup.window.close()

    qtbot.waitUntil(lambda: not setup.window.isVisible())
    assert setup.runner.killed == 0
    assert setup.runner.waited  # the second wait did not send "stop" again


def test_failure_details_open_in_a_dialog(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.start_and_wait_running()
    setup.runner.emit("Error: Invalid or corrupt jarfile server.jar")
    setup.runner.exit(1)
    qtbot.waitUntil(lambda: setup.dashboard.details_button.isVisible())

    qtbot.mouseClick(setup.dashboard.details_button, Qt.MouseButton.LeftButton)

    dialogs = [widget for widget in QApplication.topLevelWidgets() if isinstance(widget, ErrorDetailsDialog)]
    assert dialogs
    assert "Invalid or corrupt jarfile" in dialogs[-1].details.toPlainText()
    assert "exit code: 1" in dialogs[-1].details.toPlainText()
    for dialog in dialogs:
        dialog.close()
