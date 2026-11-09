"""Tests for the bounded server console-output buffer."""

from threading import Thread

import pytest

from mcserver.application.ports import OutputStream, ServerOutputLine
from mcserver.application.server_output import ServerOutputBuffer


def texts(lines: tuple[ServerOutputLine, ...] | list[ServerOutputLine]) -> list[str]:
    return [line.text for line in lines]


def test_publish_records_line_with_sequence_server_and_stream() -> None:
    buffer = ServerOutputBuffer(capacity=10)

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


def test_snapshot_filters_by_server() -> None:
    buffer = ServerOutputBuffer()
    buffer.publish("survival", OutputStream.STDOUT, "a")
    buffer.publish("creative", OutputStream.STDOUT, "b")

    assert texts(buffer.snapshot("creative")) == ["b"]


def test_subscribe_replays_buffer_then_delivers_live_lines() -> None:
    buffer = ServerOutputBuffer()
    buffer.publish("survival", OutputStream.STDOUT, "old")
    received: list[ServerOutputLine] = []

    buffer.subscribe(received.append)
    buffer.publish("survival", OutputStream.STDOUT, "new")

    assert texts(received) == ["old", "new"]


def test_subscribe_without_replay_receives_only_live_lines() -> None:
    buffer = ServerOutputBuffer()
    buffer.publish("survival", OutputStream.STDOUT, "old")
    received: list[ServerOutputLine] = []

    buffer.subscribe(received.append, replay=False)
    buffer.publish("survival", OutputStream.STDOUT, "new")

    assert texts(received) == ["new"]


def test_unsubscribe_stops_delivery_and_is_idempotent() -> None:
    buffer = ServerOutputBuffer()
    received: list[ServerOutputLine] = []
    unsubscribe = buffer.subscribe(received.append)

    unsubscribe()
    unsubscribe()
    buffer.publish("survival", OutputStream.STDOUT, "ignored")

    assert received == []


def test_failing_listener_does_not_block_other_listeners_or_buffering() -> None:
    buffer = ServerOutputBuffer()
    received: list[ServerOutputLine] = []

    def broken(_line: ServerOutputLine) -> None:
        raise RuntimeError("listener bug")

    buffer.subscribe(broken)
    buffer.subscribe(received.append)
    buffer.publish("survival", OutputStream.STDOUT, "still delivered")

    assert texts(received) == ["still delivered"]
    assert texts(buffer.snapshot()) == ["still delivered"]


def test_listener_may_unsubscribe_itself_during_delivery() -> None:
    buffer = ServerOutputBuffer()
    received: list[ServerOutputLine] = []
    unsubscribe = None

    def once(line: ServerOutputLine) -> None:
        received.append(line)
        assert unsubscribe is not None
        unsubscribe()

    unsubscribe = buffer.subscribe(once, replay=False)
    buffer.publish("survival", OutputStream.STDOUT, "first")
    buffer.publish("survival", OutputStream.STDOUT, "second")

    assert texts(received) == ["first"]


def test_clear_discards_lines_but_keeps_subscriptions_and_sequence() -> None:
    buffer = ServerOutputBuffer()
    received: list[ServerOutputLine] = []
    buffer.subscribe(received.append)
    buffer.publish("survival", OutputStream.STDOUT, "before")

    buffer.clear()
    buffer.publish("survival", OutputStream.STDOUT, "after")

    assert texts(buffer.snapshot()) == ["after"]
    assert buffer.snapshot()[0].sequence == 2
    assert texts(received) == ["before", "after"]


def test_concurrent_publishers_and_late_subscriber_see_each_line_once_in_order() -> None:
    buffer = ServerOutputBuffer(capacity=10_000)
    received: list[ServerOutputLine] = []

    def publish_many(stream: OutputStream) -> None:
        for index in range(500):
            buffer.publish("survival", stream, str(index))

    threads = [Thread(target=publish_many, args=(stream,)) for stream in OutputStream]
    for thread in threads:
        thread.start()
    buffer.subscribe(received.append)
    for thread in threads:
        thread.join()

    sequences = [line.sequence for line in received]
    assert sequences == list(range(1, 1001))
