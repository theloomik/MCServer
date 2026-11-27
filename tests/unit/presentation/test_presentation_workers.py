"""Tests for running backend calls in the background and returning to the GUI thread."""

from threading import Event, current_thread, main_thread

from PySide6.QtCore import QThreadPool
from pytestqt.qtbot import QtBot

from mcserver.application.errors import ServerStartFailed
from mcserver.presentation.errors import describe_error, technical_details
from mcserver.presentation.workers import BackgroundRunner


def test_success_runs_function_off_gui_thread_and_callback_on_it(qtbot: QtBot) -> None:
    runner = BackgroundRunner()
    worker_threads: list[bool] = []
    results: list[tuple[object, bool]] = []

    def work() -> int:
        worker_threads.append(current_thread() is main_thread())
        return 42

    runner.run(work, lambda result: results.append((result, current_thread() is main_thread())), lambda _e: None)

    qtbot.waitUntil(lambda: results != [])
    assert worker_threads == [False]
    assert results == [(42, True)]
    assert runner.pending == 0


def test_failure_is_delivered_on_gui_thread(qtbot: QtBot) -> None:
    runner = BackgroundRunner()
    errors: list[tuple[BaseException, bool]] = []
    failure = ServerStartFailed("survival")

    def work() -> None:
        raise failure

    runner.run(work, lambda _r: None, lambda error: errors.append((error, current_thread() is main_thread())))

    qtbot.waitUntil(lambda: errors != [])
    assert errors == [(failure, True)]


def test_results_after_dispose_are_dropped(qtbot: QtBot) -> None:
    runner = BackgroundRunner()
    gate = Event()
    results: list[object] = []
    runner.run(lambda: gate.wait(5), results.append, results.append)

    runner.dispose()
    gate.set()
    QThreadPool.globalInstance().waitForDone(5000)
    qtbot.wait(50)

    assert results == []


def test_describe_error_maps_backend_errors_and_keeps_cause_details() -> None:
    try:
        try:
            raise FileNotFoundError("java.exe")
        except FileNotFoundError as cause:
            raise ServerStartFailed("survival") from cause
    except ServerStartFailed as error:
        message = describe_error(error)

    assert message.key == "errors.start_failed"
    assert message.params == {"server_id": "survival"}
    assert message.details.splitlines() == [
        "ServerStartFailed: Could not start server 'survival'.",
        "FileNotFoundError: java.exe",
    ]


def test_unknown_errors_get_generic_message() -> None:
    message = describe_error(RuntimeError("boom"))

    assert message.key == "errors.unexpected"
    assert technical_details(RuntimeError()) == "RuntimeError"
