"""Monitoring and the coordinator hooks M3 relies on (M3-BE-02, M3-BE-03)."""

from __future__ import annotations

import os
from threading import Thread

from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_metrics import ProcessSample, ServerMetrics
from mcserver.domain.lifecycle import ServerState
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.psutil_metrics import PsutilProcessMetrics
from tests.runtime_fakes import FakeRunner, FakeRunnerFactory, ManualScheduler


class Repository:
    def get(self, server_id: str) -> ServerConfiguration:
        return ServerConfiguration(server_id, server_id, "paper.jar", 4096)


class Source:
    def __init__(self, sample: ProcessSample | None) -> None:
        self.value = sample
        self.asked: list[int] = []

    def sample(self, process_id: int) -> ProcessSample | None:
        self.asked.append(process_id)
        return self.value


def coordinator_at(times: list[float]) -> tuple[ServerCoordinator, FakeRunnerFactory]:
    factory = FakeRunnerFactory(FakeRunner(auto_ready=True))
    return ServerCoordinator(factory, scheduler=ManualScheduler(), clock=lambda: times[0]), factory


def test_metrics_combine_process_sample_memory_setting_and_uptime() -> None:
    times = [100.0]
    coordinator, _ = coordinator_at(times)
    source = Source(ProcessSample(12.345, 1536 * 1024 * 1024))
    metrics = ServerMetrics(coordinator, source, Repository(), lambda: times[0])  # type: ignore[arg-type]
    assert metrics.sample() is None

    coordinator.start_server("survival")
    times[0] = 175.9

    snapshot = metrics.sample()

    assert snapshot is not None
    assert (snapshot.server_id, snapshot.state) == ("survival", ServerState.RUNNING)
    assert (snapshot.cpu_percent, snapshot.memory_mb, snapshot.allocated_mb, snapshot.uptime_seconds) == (
        12.3,
        1536.0,
        4096,
        75,
    )
    assert source.asked == [4242]


def test_metrics_are_none_when_the_process_is_gone() -> None:
    coordinator, _ = coordinator_at([0.0])
    coordinator.start_server("survival")

    assert ServerMetrics(coordinator, Source(None), Repository(), lambda: 0.0).sample() is None  # type: ignore[arg-type]


def test_psutil_measures_this_process() -> None:
    metrics = PsutilProcessMetrics()

    first = metrics.sample(os.getpid())
    second = metrics.sample(os.getpid())

    assert first is not None and second is not None
    assert second.memory_bytes > 10 * 1024 * 1024
    assert 0.0 <= second.cpu_percent <= 100.0
    assert metrics.sample(2**31 - 1) is None


def test_waiting_for_a_console_line_sees_the_reply_to_the_command() -> None:
    coordinator, factory = coordinator_at([0.0])
    coordinator.start_server("survival")
    runner = factory.runner

    def reply() -> None:
        while "save-all flush" not in runner.commands:
            pass
        runner.emit("[Server thread/INFO]: Saved the game")

    thread = Thread(target=reply)
    thread.start()
    assert coordinator.send_and_wait_for_line("survival", "save-all flush", lambda line: "Saved the game" in line, 5)
    thread.join()
    assert not coordinator.send_and_wait_for_line("survival", "save-all flush", lambda line: "never" in line, 0.05)
