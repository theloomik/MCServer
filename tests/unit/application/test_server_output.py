"""Tests for the bounded server console-output buffer."""

from collections.abc import Callable, Iterator
from threading import Barrier, Event, Thread
from threading import enumerate as enumerate_threads
from time import monotonic, sleep

import pytest

from mcserver.application.ports import OutputStream, ServerOutputLine
from mcserver.application.server_output import ServerOutputBuffer

WAIT = 3.0


@pytest.fixture
def buffer() -> Iterator[ServerOutputBuffer]:
    output = ServerOutputBuffer(capacity=10_000)
    yield output
    output.close(WAIT)


def texts(lines: tuple[ServerOutputLine, ...] | list[ServerOutputLine]) -> list[str]:
    return [line.text for line in lines]


def sequences(lines: list[ServerOutputLine]) -> list[int]:
    return [line.sequence for line in lines]


def run_with_timeout(action: Callable[[], None], timeout: float = WAIT) -> bool:
    """Run ``action`` in a thread and report whether it finished in time (no deadlock)."""
    worker = Thread(target=action, daemon=True)
    worker.start()
    worker.join(timeout)
    return not worker.is_alive()


# --- buffering ------------------------------------------------------------


def test_publish_records_line_with_sequence_server_and_stream(buffer: ServerOutputBuffer) -> None:
    buffer.publish("survival", OutputStream.STDOUT, "Done (3.2s)!")
    buffer.publish("survival", OutputStream.STDERR, "warning")

    assert buffer.snapshot() == (
        ServerOutputLine(1, "survival", OutputStream.STDOUT, "Done (3.2s)!"),
        ServerOutputLine(2, "survival", OutputStream.STDERR, "warning"),
    )


def test_buffer_keeps_only_most_recent_lines() -> None:
    buffer = ServerOutputBuffer(capacity=3)

    for index in range(5):
        buffer.publish("survival", OutputStream.STDOUT, f"line {index}")

    assert texts(buffer.snapshot()) == ["line 2", "line 3", "line 4"]
    assert [line.sequence for line in buffer.snapshot()] == [3, 4, 5]


def test_rejects_non_positive_capacity() -> None:
    with pytest.raises(ValueError, match="capacity"):
        ServerOutputBuffer(capacity=0)


def test_snapshot_filters_by_server(buffer: ServerOutputBuffer) -> None:
    buffer.publish("survival", OutputStream.STDOUT, "a")
    buffer.publish("creative", OutputStream.STDOUT, "b")

    assert texts(buffer.snapshot("creative")) == ["b"]


# --- subscriptions --------------------------------------------------------


def test_subscribe_replays_buffer_then_delivers_live_lines(buffer: ServerOutputBuffer) -> None:
    buffer.publish("survival", OutputStream.STDOUT, "old")
    received: list[ServerOutputLine] = []

    buffer.subscribe(received.append)
    buffer.publish("survival", OutputStream.STDOUT, "new")

    assert buffer.flush(WAIT)
    assert texts(received) == ["old", "new"]


def test_subscribe_without_replay_receives_only_live_lines(buffer: ServerOutputBuffer) -> None:
    buffer.publish("survival", OutputStream.STDOUT, "old")
    received: list[ServerOutputLine] = []

    buffer.subscribe(received.append, replay=False)
    buffer.publish("survival", OutputStream.STDOUT, "new")

    assert buffer.flush(WAIT)
    assert texts(received) == ["new"]


def test_unsubscribe_stops_delivery_and_is_idempotent(buffer: ServerOutputBuffer) -> None:
    received: list[ServerOutputLine] = []
    unsubscribe = buffer.subscribe(received.append)

    unsubscribe()
    unsubscribe()
    buffer.publish("survival", OutputStream.STDOUT, "ignored")

    assert buffer.flush(WAIT)
    assert received == []


def test_failing_listener_does_not_block_other_listeners_or_buffering(buffer: ServerOutputBuffer) -> None:
    received: list[ServerOutputLine] = []

    def broken(_line: ServerOutputLine) -> None:
        raise RuntimeError("listener bug")

    buffer.subscribe(broken)
    buffer.subscribe(received.append)
    buffer.publish("survival", OutputStream.STDOUT, "still delivered")

    assert buffer.flush(WAIT)
    assert texts(received) == ["still delivered"]
    assert texts(buffer.snapshot()) == ["still delivered"]


def test_failing_listener_counts_line_as_delivered_and_keeps_receiving(
    buffer: ServerOutputBuffer, caplog: pytest.LogCaptureFixture
) -> None:
    attempts: list[int] = []
    healthy: list[ServerOutputLine] = []

    def always_fails(line: ServerOutputLine) -> None:
        attempts.append(line.sequence)
        raise ValueError(f"cannot handle {line.text}")

    buffer.subscribe(always_fails)
    buffer.subscribe(healthy.append)
    for index in range(3):
        buffer.publish("survival", OutputStream.STDOUT, str(index))

    assert buffer.flush(WAIT)
    assert attempts == [1, 2, 3]  # one attempt per line, no retry, still subscribed
    assert sequences(healthy) == [1, 2, 3]
    assert caplog.text.count("Server output listener failed.") == 3


def test_listener_raising_base_exception_does_not_kill_dispatcher(buffer: ServerOutputBuffer) -> None:
    healthy: list[ServerOutputLine] = []

    def exits(line: ServerOutputLine) -> None:
        if line.sequence == 1:
            raise SystemExit(1)

    buffer.subscribe(exits)
    buffer.subscribe(healthy.append)
    buffer.publish("survival", OutputStream.STDOUT, "first")
    assert buffer.flush(WAIT)
    buffer.publish("survival", OutputStream.STDOUT, "second")

    assert buffer.flush(WAIT)
    assert texts(healthy) == ["first", "second"]


def test_clear_discards_lines_but_keeps_subscriptions_and_sequence(buffer: ServerOutputBuffer) -> None:
    received: list[ServerOutputLine] = []
    buffer.subscribe(received.append)
    buffer.publish("survival", OutputStream.STDOUT, "before")
    assert buffer.flush(WAIT)

    buffer.clear()
    buffer.publish("survival", OutputStream.STDOUT, "after")

    assert buffer.flush(WAIT)
    assert texts(buffer.snapshot()) == ["after"]
    assert buffer.snapshot()[0].sequence == 2
    assert texts(received) == ["before", "after"]


def dispatcher_threads() -> list[Thread]:
    return [thread for thread in enumerate_threads() if thread.name == "server-output-dispatcher"]


def test_close_stops_dispatcher_and_rejects_new_subscriptions() -> None:
    buffer = ServerOutputBuffer()
    received: list[ServerOutputLine] = []
    buffer.subscribe(received.append)
    dispatcher = buffer._dispatcher
    assert dispatcher is not None and dispatcher.is_alive()

    assert buffer.close(WAIT) is True
    buffer.publish("survival", OutputStream.STDOUT, "after close")

    assert not dispatcher.is_alive()
    assert dispatcher not in dispatcher_threads()
    assert received == []
    assert texts(buffer.snapshot()) == ["after close"]
    assert buffer.close(WAIT) is True  # idempotent
    with pytest.raises(RuntimeError, match="closed"):
        buffer.subscribe(received.append)


def test_close_without_subscribers_starts_no_thread() -> None:
    before = len(dispatcher_threads())
    buffer = ServerOutputBuffer()
    buffer.publish("survival", OutputStream.STDOUT, "x")

    assert len(dispatcher_threads()) == before
    assert buffer.close(WAIT) is True


def test_close_reports_listener_still_blocked_then_thread_ends_after_release() -> None:
    buffer = ServerOutputBuffer()
    in_listener = Event()
    release = Event()
    after_first: list[ServerOutputLine] = []

    def blocked(line: ServerOutputLine) -> None:
        if line.sequence == 1:
            in_listener.set()
            release.wait(WAIT)
        else:
            after_first.append(line)

    buffer.subscribe(blocked)
    buffer.publish("survival", OutputStream.STDOUT, "first")
    assert in_listener.wait(WAIT)
    buffer.publish("survival", OutputStream.STDOUT, "dropped on close")

    assert buffer.close(0.05) is False
    release.set()
    assert buffer.close(WAIT) is True
    assert after_first == []


# --- slow listener --------------------------------------------------------


def test_slow_listener_does_not_block_publishers(buffer: ServerOutputBuffer) -> None:
    release = Event()
    received: list[ServerOutputLine] = []

    def slow(line: ServerOutputLine) -> None:
        release.wait(WAIT)
        received.append(line)

    buffer.subscribe(slow)
    started = monotonic()
    for index in range(200):
        buffer.publish("survival", OutputStream.STDOUT, str(index))
    publish_duration = monotonic() - started

    assert publish_duration < 1.0
    assert len(buffer.snapshot()) == 200
    release.set()
    assert buffer.flush(WAIT)
    assert sequences(received) == list(range(1, 201))


def test_blocked_listener_delays_other_listeners_but_not_publish(buffer: ServerOutputBuffer) -> None:
    """Documents the shared-dispatcher trade-off: others wait, the process reader never does."""
    in_listener = Event()
    release = Event()
    slow_received: list[ServerOutputLine] = []
    other_received: list[ServerOutputLine] = []

    def slow(line: ServerOutputLine) -> None:
        in_listener.set()
        release.wait(WAIT)
        slow_received.append(line)

    buffer.subscribe(slow)
    buffer.subscribe(other_received.append)
    buffer.publish("survival", OutputStream.STDOUT, "0")
    assert in_listener.wait(WAIT)

    started = monotonic()
    for index in range(1, 500):
        buffer.publish("survival", OutputStream.STDOUT, str(index))
    publish_duration = monotonic() - started
    sleep(0.1)  # give the dispatcher a chance to (wrongly) deliver to the other listener

    try:
        assert publish_duration < 1.0
        assert len(buffer.snapshot()) == 500
        assert other_received == []
    finally:
        release.set()
    assert buffer.flush(WAIT)
    assert sequences(slow_received) == list(range(1, 501))
    assert sequences(other_received) == list(range(1, 501))


def test_slow_listener_does_not_block_buffer_reads_from_other_threads(buffer: ServerOutputBuffer) -> None:
    in_listener = Event()
    release = Event()

    def slow(_line: ServerOutputLine) -> None:
        in_listener.set()
        release.wait(WAIT)

    buffer.subscribe(slow)
    buffer.publish("survival", OutputStream.STDOUT, "x")
    assert in_listener.wait(WAIT)

    def other_thread_calls() -> None:
        buffer.snapshot()
        buffer.subscribe(lambda _line: None)()
        buffer.publish("survival", OutputStream.STDOUT, "y")
        buffer.clear()

    try:
        assert run_with_timeout(other_thread_calls)
    finally:
        release.set()


def test_listener_waiting_on_thread_that_uses_buffer_does_not_deadlock(buffer: ServerOutputBuffer) -> None:
    """Models a UI listener that blocks on the GUI thread while the GUI reads the buffer."""
    in_listener = Event()
    gui_done = Event()
    finished: list[bool] = []

    def blocking_listener(_line: ServerOutputLine) -> None:
        in_listener.set()
        finished.append(gui_done.wait(WAIT))

    def gui_thread() -> None:
        in_listener.wait(WAIT)
        buffer.snapshot()
        gui_done.set()

    buffer.subscribe(blocking_listener)
    buffer.publish("survival", OutputStream.STDOUT, "x")

    assert run_with_timeout(gui_thread)
    assert buffer.flush(WAIT)
    assert finished == [True]


def test_listener_lagging_beyond_capacity_skips_evicted_lines_in_order() -> None:
    buffer = ServerOutputBuffer(capacity=5)
    release = Event()
    received: list[ServerOutputLine] = []

    def slow(line: ServerOutputLine) -> None:
        release.wait(WAIT)
        received.append(line)

    buffer.subscribe(slow)
    buffer.publish("survival", OutputStream.STDOUT, "first")
    for index in range(20):
        buffer.publish("survival", OutputStream.STDOUT, str(index))
    release.set()

    try:
        assert buffer.flush(WAIT)
        delivered = sequences(received)
        assert delivered == sorted(set(delivered))
        assert delivered[-5:] == [17, 18, 19, 20, 21]
        assert len(delivered) < 21
    finally:
        buffer.close(WAIT)


# --- re-entrancy ----------------------------------------------------------


def test_listener_may_call_buffer_methods_without_deadlock(buffer: ServerOutputBuffer) -> None:
    calls: list[str] = []
    nested: list[ServerOutputLine] = []
    unsubscribe_self = None

    def reentrant(line: ServerOutputLine) -> None:
        calls.append(f"snapshot:{texts(buffer.snapshot())}")
        buffer.subscribe(nested.append, replay=True)
        buffer.clear()
        buffer.publish("survival", OutputStream.STDERR, "from listener")
        assert unsubscribe_self is not None
        unsubscribe_self()

    unsubscribe_self = buffer.subscribe(reentrant, replay=False)
    buffer.publish("survival", OutputStream.STDOUT, "trigger")

    assert buffer.flush(WAIT)
    assert calls == ["snapshot:['trigger']"]
    assert texts(nested) == ["from listener"]
    assert texts(buffer.snapshot()) == ["from listener"]


def test_listener_may_unsubscribe_itself_during_delivery(buffer: ServerOutputBuffer) -> None:
    received: list[ServerOutputLine] = []
    unsubscribe = None

    def once(line: ServerOutputLine) -> None:
        received.append(line)
        assert unsubscribe is not None
        unsubscribe()

    unsubscribe = buffer.subscribe(once, replay=False)
    buffer.publish("survival", OutputStream.STDOUT, "first")
    buffer.publish("survival", OutputStream.STDOUT, "second")

    assert buffer.flush(WAIT)
    assert texts(received) == ["first"]


def test_publish_from_listener_keeps_order_for_every_subscriber(buffer: ServerOutputBuffer) -> None:
    echoed: list[ServerOutputLine] = []
    observer: list[ServerOutputLine] = []

    def echo(line: ServerOutputLine) -> None:
        echoed.append(line)
        if line.stream is OutputStream.STDOUT:
            buffer.publish("survival", OutputStream.STDERR, f"echo {line.text}")

    buffer.subscribe(echo)
    buffer.subscribe(observer.append)
    for index in range(3):
        buffer.publish("survival", OutputStream.STDOUT, str(index))

    assert buffer.flush(WAIT)
    for received in (echoed, observer):
        assert sequences(received) == list(range(1, 7))
    assert sorted(texts(observer)) == sorted(["0", "1", "2", "echo 0", "echo 1", "echo 2"])


def test_flush_and_close_from_listener_are_rejected(buffer: ServerOutputBuffer) -> None:
    errors: list[str] = []

    def listener(_line: ServerOutputLine) -> None:
        for method in (buffer.flush, buffer.close):
            try:
                method()
            except RuntimeError as error:
                errors.append(str(error))

    buffer.subscribe(listener)
    buffer.publish("survival", OutputStream.STDOUT, "x")

    assert buffer.flush(WAIT)
    assert errors == [
        "flush() cannot be called from an output listener.",
        "close() cannot be called from an output listener.",
    ]


# --- concurrency ----------------------------------------------------------


def test_concurrent_publishers_and_subscribers_get_gap_free_ordered_lines(buffer: ServerOutputBuffer) -> None:
    publishers = 4
    lines_per_publisher = 500
    total = publishers * lines_per_publisher
    replaying: list[list[ServerOutputLine]] = [[] for _ in range(4)]
    live_only: list[list[ServerOutputLine]] = [[] for _ in range(4)]
    start = Barrier(publishers + len(replaying) + len(live_only))

    def publish_many(publisher: int) -> None:
        start.wait()
        for index in range(lines_per_publisher):
            buffer.publish(f"server-{publisher}", OutputStream.STDOUT, str(index))

    def subscribe_later(target: list[ServerOutputLine], replay: bool) -> None:
        start.wait()
        buffer.subscribe(target.append, replay=replay)

    threads = [Thread(target=publish_many, args=(index,)) for index in range(publishers)]
    threads += [Thread(target=subscribe_later, args=(target, True)) for target in replaying]
    threads += [Thread(target=subscribe_later, args=(target, False)) for target in live_only]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT)

    assert buffer.flush(WAIT)
    for received in replaying:
        assert sequences(received) == list(range(1, total + 1))
    for received in live_only:
        delivered = sequences(received)
        first = delivered[0] if delivered else total + 1
        assert delivered == list(range(first, total + 1))
    for publisher in range(publishers):
        per_server = [line.text for line in buffer.snapshot(f"server-{publisher}")]
        assert per_server == [str(index) for index in range(lines_per_publisher)]
