"""Windows session end and unhandled exceptions follow the graceful-stop policy (ADR 0006)."""

from __future__ import annotations

from fakes import FakeRunner, FakeRunnerFactory, coordinator

from mcserver.presentation.adapters.session_end import CrashHandler, SessionEndHandler


class RecordingBlocker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def block(self, window_handle: int, reason: str) -> None:
        self.calls.append(f"block:{window_handle}:{reason}")

    def unblock(self, window_handle: int) -> None:
        self.calls.append(f"unblock:{window_handle}")


def test_session_end_stops_the_server_gracefully_while_blocking_shutdown() -> None:
    factory = FakeRunnerFactory()
    server = coordinator(factory)
    server.start_server("survival")
    blocker = RecordingBlocker()

    SessionEndHandler(server, "saving", lambda: 42, blocker)()

    assert factory.runner.stopped == [90.0] and factory.runner.killed == 0
    assert server.active_server_id is None
    assert blocker.calls == ["block:42:saving", "unblock:42"]


def test_session_end_unblocks_even_when_the_stop_times_out() -> None:
    factory = FakeRunnerFactory(FakeRunner(stop_exits=False))
    server = coordinator(factory)
    server.start_server("survival")
    blocker = RecordingBlocker()

    SessionEndHandler(server, "saving", lambda: 42, blocker)()

    assert blocker.calls[-1] == "unblock:42"
    assert factory.runner.killed == 0


def test_session_end_without_a_server_does_nothing() -> None:
    blocker = RecordingBlocker()
    SessionEndHandler(coordinator(), "saving", lambda: 42, blocker)()
    assert blocker.calls == []


def test_crash_handler_tries_one_short_graceful_stop_then_exits() -> None:
    factory = FakeRunnerFactory(FakeRunner(stop_exits=False))
    server = coordinator(factory)
    server.start_server("survival")
    exits: list[int] = []
    handler = CrashHandler(server, exits.append, stop_timeout=30.0)

    handler(RuntimeError, RuntimeError("boom"), None)
    handler(RuntimeError, RuntimeError("again"), None)  # only the first exception acts

    assert factory.runner.stopped == [30.0]
    assert factory.runner.killed == 0  # the Job Object ends Java only when MCServer itself exits
    assert exits == [1]
    assert handler.crashed
    assert server.active_server_id == "survival"


def test_crash_handler_without_a_server_just_exits() -> None:
    exits: list[int] = []
    CrashHandler(None, exits.append)(ValueError, ValueError("bad"), None)
    assert exits == [1]
