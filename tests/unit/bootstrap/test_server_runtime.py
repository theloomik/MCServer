"""Tests for composing the server runtime without launching Java."""

from pathlib import Path

import pytest

from mcserver.application.errors import ServerStopFailed
from mcserver.application.ports import OutputStream, ProcessExitHandler, ServerRunner
from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_output import ServerOutputBuffer
from mcserver.bootstrap.server_runtime import ServerRuntime, build_server_coordinator, build_server_runtime
from mcserver.infrastructure.java_runtime import JavaRuntime, JavaRuntimeResolver, JavaRuntimeSource

WAIT = 3.0


class StubJavaResolver(JavaRuntimeResolver):
    """Return a fixed Java path without probing the system."""

    def resolve(self) -> JavaRuntime:
        return JavaRuntime(Path("java"), JavaRuntimeSource.SYSTEM)


class FakeRunner:
    def __init__(self, fail_on_stop: bool = False) -> None:
        self.fail_on_stop = fail_on_stop
        self.stopped_with: float | None = None

    def start(self, server_id: str, on_exit: ProcessExitHandler) -> None:
        pass

    def stop(self, timeout: float) -> None:
        self.stopped_with = timeout
        if self.fail_on_stop:
            raise RuntimeError("stop failed")


class FakeFactory:
    def __init__(self, runner: FakeRunner) -> None:
        self.runner = runner

    def create(self, server_id: str) -> ServerRunner:
        return self.runner


def runtime_with(runner: FakeRunner) -> ServerRuntime:
    return ServerRuntime(coordinator=ServerCoordinator(FakeFactory(runner)), output=ServerOutputBuffer())


def test_runtime_shares_one_output_buffer_with_runner_factory(tmp_path: Path) -> None:
    with build_server_runtime(tmp_path, StubJavaResolver(), output_capacity=50) as runtime:
        assert isinstance(runtime.coordinator, ServerCoordinator)
        assert isinstance(runtime.output, ServerOutputBuffer)
        assert runtime.output.capacity == 50
        assert runtime.coordinator._runner_factory._output_sink is runtime.output  # type: ignore[attr-defined]


def test_build_server_coordinator_remains_available(tmp_path: Path) -> None:
    assert isinstance(build_server_coordinator(tmp_path, StubJavaResolver()), ServerCoordinator)


def test_close_stops_active_server_and_ends_dispatcher_thread() -> None:
    runner = FakeRunner()
    runtime = runtime_with(runner)
    runtime.output.subscribe(lambda _line: None)
    dispatcher = runtime.output._dispatcher
    runtime.coordinator.start_server("survival")

    assert runtime.close(timeout=WAIT) is True

    assert runner.stopped_with == WAIT
    assert runtime.coordinator.active_server_id is None
    assert dispatcher is not None and not dispatcher.is_alive()


def test_close_without_active_server_or_subscribers_is_safe() -> None:
    runtime = runtime_with(FakeRunner())

    assert runtime.close(timeout=WAIT) is True
    assert runtime.close(timeout=WAIT) is True


def test_close_ends_dispatcher_even_when_server_stop_fails() -> None:
    runtime = runtime_with(FakeRunner(fail_on_stop=True))
    runtime.output.subscribe(lambda _line: None)
    dispatcher = runtime.output._dispatcher
    runtime.coordinator.start_server("survival")

    with pytest.raises(ServerStopFailed):
        runtime.close(timeout=WAIT)

    assert dispatcher is not None and not dispatcher.is_alive()
    with pytest.raises(RuntimeError, match="closed"):
        runtime.output.subscribe(lambda _line: None)


def test_context_manager_closes_runtime() -> None:
    received: list[str] = []
    with runtime_with(FakeRunner()) as runtime:
        runtime.output.subscribe(lambda line: received.append(line.text))
        runtime.output.publish("survival", OutputStream.STDOUT, "hello")
        assert runtime.output.flush(WAIT)
        dispatcher = runtime.output._dispatcher

    assert received == ["hello"]
    assert dispatcher is not None and not dispatcher.is_alive()
