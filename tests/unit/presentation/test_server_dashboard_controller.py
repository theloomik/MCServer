"""Tests for start/stop orchestration, using the real coordinator with a fake runner."""

from threading import Event

import pytest
from fakes import FakeRunnerFactory, coordinator
from pytestqt.qtbot import QtBot

from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.presentation.adapters.status_poller import StatusPoller
from mcserver.presentation.controllers.server_dashboard import (
    STOP_TIMEOUT_SECONDS,
    DashboardState,
    Operation,
    ServerDashboardController,
)
from mcserver.presentation.controllers.server_list import ServerRow, ServerStatus
from mcserver.presentation.i18n import en
from mcserver.presentation.workers import BackgroundRunner

SURVIVAL = ServerRow(ServerConfiguration("survival", "survival", "paper.jar", 4096), ServerStatus.STOPPED)
CREATIVE = ServerRow(ServerConfiguration("creative", "creative", "paper.jar", 2048), ServerStatus.STOPPED)


class Harness:
    def __init__(self, factory: FakeRunnerFactory | None = None) -> None:
        self.factory = factory or FakeRunnerFactory()
        self.coordinator = coordinator(self.factory)
        self.poller = StatusPoller(self.coordinator, interval_ms=20)
        self.controller = ServerDashboardController(self.coordinator, self.poller, BackgroundRunner())
        self.states: list[DashboardState] = []
        self.controller.state_changed.connect(self.states.append)
        self.poller.start()

    @property
    def runner(self):  # type: ignore[no-untyped-def]
        return self.factory.runner

    @property
    def state(self) -> DashboardState:
        return self.controller.state


@pytest.fixture
def harness(qtbot: QtBot) -> Harness:
    built = Harness()
    yield built
    built.poller.stop()


def test_selecting_a_server_shows_it_stopped_and_startable(harness: Harness) -> None:
    harness.controller.show_server(SURVIVAL)

    state = harness.state
    assert state.row == SURVIVAL
    assert state.status is ServerStatus.STOPPED
    assert state.java_available and state.can_start and not state.can_stop


def test_start_runs_in_background_and_reaches_running(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.show_server(SURVIVAL)

    harness.controller.start()

    assert harness.state.operation is Operation.STARTING
    assert not harness.state.can_start and not harness.state.can_stop
    qtbot.waitUntil(lambda: harness.state.status is ServerStatus.RUNNING and harness.state.operation is None)
    assert harness.runner.started == ["survival"]
    assert harness.state.can_stop and not harness.state.can_start
    assert harness.coordinator.active_server_id == "survival"


def test_stop_succeeds_without_unexpected_stop_notice(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.show_server(SURVIVAL)
    harness.controller.start()
    qtbot.waitUntil(lambda: harness.state.can_stop)

    harness.controller.stop()

    assert harness.state.operation is Operation.STOPPING
    qtbot.waitUntil(lambda: harness.state.status is ServerStatus.STOPPED and harness.state.operation is None)
    assert harness.runner.stopped == [STOP_TIMEOUT_SECONDS]
    assert harness.state.notice is None and harness.state.error is None
    assert harness.state.can_start


def test_start_failure_shows_message_and_leaves_server_startable(qtbot: QtBot, harness: Harness) -> None:
    harness.runner.start_error = FileNotFoundError("java.exe")
    harness.controller.show_server(SURVIVAL)

    harness.controller.start()

    qtbot.waitUntil(lambda: harness.state.error is not None)
    error = harness.state.error
    assert error is not None and error.key == "errors.start_failed"
    assert "FileNotFoundError: java.exe" in error.details
    assert harness.state.status is ServerStatus.STOPPED and harness.state.can_start
    assert harness.coordinator.active_server_id is None


def test_stop_failure_shows_warning(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.show_server(SURVIVAL)
    harness.controller.start()
    qtbot.waitUntil(lambda: harness.state.can_stop)
    harness.runner.stop_error = OSError("access denied")

    harness.controller.stop()

    qtbot.waitUntil(lambda: harness.state.error is not None)
    assert harness.state.error is not None and harness.state.error.key == "errors.stop_failed"
    assert harness.state.operation is None


def test_repeated_requests_are_ignored_while_an_operation_runs(qtbot: QtBot, harness: Harness) -> None:
    harness.runner.start_gate = Event()
    harness.controller.show_server(SURVIVAL)

    harness.controller.start()
    harness.controller.start()
    harness.controller.stop()
    assert harness.controller.busy
    harness.runner.start_gate.set()

    qtbot.waitUntil(lambda: harness.state.status is ServerStatus.RUNNING and not harness.controller.busy)
    assert harness.runner.started == ["survival"]
    assert harness.runner.stopped == []


def test_other_active_server_blocks_start(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.show_server(SURVIVAL)
    harness.controller.start()
    qtbot.waitUntil(lambda: harness.state.status is ServerStatus.RUNNING)

    harness.controller.show_server(CREATIVE)

    state = harness.state
    assert state.status is ServerStatus.STOPPED
    assert state.other_active_server == "survival"
    assert not state.can_start and not state.can_stop
    harness.controller.start()
    assert harness.runner.started == ["survival"]


def test_switching_servers_keeps_errors_per_server(qtbot: QtBot, harness: Harness) -> None:
    harness.runner.start_error = RuntimeError("boom")
    harness.controller.show_server(SURVIVAL)
    harness.controller.start()
    qtbot.waitUntil(lambda: harness.state.error is not None)

    harness.controller.show_server(CREATIVE)
    assert harness.state.error is None
    harness.controller.show_server(SURVIVAL)
    assert harness.state.error is not None


def test_unexpected_exit_is_reported_once_for_that_server(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.show_server(SURVIVAL)
    harness.controller.start()
    qtbot.waitUntil(lambda: harness.state.status is ServerStatus.RUNNING)

    harness.runner.exit(1)  # the process dies on its own

    qtbot.waitUntil(lambda: harness.state.notice is not None)
    notice = harness.state.notice
    assert notice is not None and notice.key == "dashboard.notice.stopped_unexpectedly"
    assert notice.params == {"server_id": "survival"}
    assert harness.state.status is ServerStatus.STOPPED and harness.state.can_start

    harness.controller.start()
    qtbot.waitUntil(lambda: harness.state.status is ServerStatus.RUNNING)
    assert harness.state.notice is None


def test_process_dying_before_first_poll_is_still_reported(qtbot: QtBot, harness: Harness) -> None:
    """Regression: a crash right after start must not be missed by the polling interval."""
    harness.poller.stop()  # make the race deterministic: no timer-driven poll in between
    harness.runner.crash_on_start = True
    harness.controller.show_server(SURVIVAL)

    harness.controller.start()

    qtbot.waitUntil(lambda: not harness.controller.busy)
    notice = harness.state.notice
    assert notice is not None and notice.key == "dashboard.notice.stopped_unexpectedly"
    assert harness.state.status is ServerStatus.STOPPED and harness.state.can_start


def test_active_server_id_reads_coordinator_not_the_last_poll(qtbot: QtBot, harness: Harness) -> None:
    """Regression: closing right after a start must see the server as active."""
    harness.poller.stop()
    harness.coordinator.start_server("survival")

    assert harness.controller.active_server_id == "survival"
    assert harness.poller.snapshot.active_server_id is None


def test_without_java_controls_are_disabled_and_requests_ignored(qtbot: QtBot) -> None:
    controller = ServerDashboardController(None, None, BackgroundRunner())

    controller.show_server(SURVIVAL)
    controller.start()
    controller.stop()

    state = controller.state
    assert not state.java_available
    assert state.status is ServerStatus.UNKNOWN
    assert not state.can_start and not state.can_stop and not controller.busy
    assert controller.stop_active() is False


def test_stop_active_stops_whatever_runs(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.show_server(SURVIVAL)
    harness.controller.start()
    qtbot.waitUntil(lambda: harness.state.status is ServerStatus.RUNNING)
    harness.controller.show_server(CREATIVE)

    assert harness.controller.stop_active() is True

    qtbot.waitUntil(lambda: harness.coordinator.active_server_id is None and not harness.controller.busy)


def test_every_message_key_the_dashboard_can_publish_exists() -> None:
    keys = {
        "errors.another_server_running",
        "errors.start_failed",
        "errors.stop_failed",
        "errors.unexpected",
        "dashboard.notice.stopped_unexpectedly",
    }

    assert keys <= set(en.MESSAGES)
