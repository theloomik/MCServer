"""Tests for the output bridge, console controller and console view."""

from threading import Thread, current_thread, main_thread

import pytest
from pytestqt.qtbot import QtBot

from mcserver.application.ports import OutputStream
from mcserver.application.server_output import ServerOutputBuffer
from mcserver.presentation import theme
from mcserver.presentation.adapters.output_bridge import OutputBridge
from mcserver.presentation.controllers.console import ConsoleController, ConsoleLine
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.views.server_console_view import ServerConsoleView


@pytest.fixture
def buffer() -> ServerOutputBuffer:
    output = ServerOutputBuffer()
    yield output
    output.close(5)


class Recorder:
    """Collects what the console controller hands to the view, and on which thread."""

    def __init__(self, controller: ConsoleController) -> None:
        self.lines: list[ConsoleLine] = []
        self.clears = 0
        self.on_gui_thread: list[bool] = []
        controller.lines_appended.connect(self._append)
        controller.cleared.connect(self._clear)

    def _append(self, lines: tuple[ConsoleLine, ...]) -> None:
        self.on_gui_thread.append(current_thread() is main_thread())
        self.lines.extend(lines)

    def _clear(self) -> None:
        self.clears += 1
        self.lines.clear()

    def texts(self) -> list[str]:
        return [line.text for line in self.lines]


def console_for(buffer: ServerOutputBuffer) -> tuple[ConsoleController, Recorder, OutputBridge]:
    bridge = OutputBridge(buffer)
    controller = ConsoleController(bridge, flush_interval_ms=10)
    return controller, Recorder(controller), bridge


def subscriber_count(buffer: ServerOutputBuffer) -> int:
    return len(buffer._subscriptions)  # type: ignore[attr-defined]


def test_replays_history_of_selected_server_only(qtbot: QtBot, buffer: ServerOutputBuffer) -> None:
    buffer.publish("survival", OutputStream.STDOUT, "old survival line")
    buffer.publish("creative", OutputStream.STDOUT, "creative line")
    controller, recorder, _ = console_for(buffer)

    controller.show_server("survival")

    qtbot.waitUntil(lambda: recorder.texts() == ["old survival line"])


def test_new_lines_arrive_on_gui_thread_with_stderr_flag_and_without_ansi(
    qtbot: QtBot, buffer: ServerOutputBuffer
) -> None:
    controller, recorder, _ = console_for(buffer)
    controller.show_server("survival")

    def publish_from_reader_thread() -> None:
        buffer.publish("survival", OutputStream.STDOUT, "\x1b[32mDone (1.0s)!\x1b[0m")
        buffer.publish("survival", OutputStream.STDERR, "WARN something")

    worker = Thread(target=publish_from_reader_thread)
    worker.start()
    worker.join()

    qtbot.waitUntil(lambda: len(recorder.lines) == 2)
    assert [(line.text, line.is_error) for line in recorder.lines] == [
        ("Done (1.0s)!", False),
        ("WARN something", True),
    ]
    assert all(recorder.on_gui_thread)
    assert [line.sequence for line in recorder.lines] == sorted(line.sequence for line in recorder.lines)


def test_switching_server_resubscribes_and_ignores_stale_lines(qtbot: QtBot, buffer: ServerOutputBuffer) -> None:
    controller, recorder, bridge = console_for(buffer)
    controller.show_server("survival")
    first_generation = bridge.generation
    buffer.publish("survival", OutputStream.STDOUT, "survival 1")
    qtbot.waitUntil(lambda: recorder.texts() == ["survival 1"])

    controller.show_server("creative")
    bridge.line_received.emit(first_generation, buffer.snapshot("survival")[0])  # a line still queued
    buffer.publish("creative", OutputStream.STDOUT, "creative 1")

    qtbot.waitUntil(lambda: recorder.texts() == ["creative 1"])
    qtbot.wait(30)
    assert recorder.texts() == ["creative 1"]
    assert subscriber_count(buffer) == 1


def test_clear_hides_shown_lines_without_touching_the_shared_buffer(qtbot: QtBot, buffer: ServerOutputBuffer) -> None:
    controller, recorder, _ = console_for(buffer)
    controller.show_server("survival")
    buffer.publish("survival", OutputStream.STDOUT, "before clear")
    qtbot.waitUntil(lambda: recorder.texts() == ["before clear"])

    controller.clear()
    buffer.publish("survival", OutputStream.STDOUT, "after clear")

    qtbot.waitUntil(lambda: recorder.texts() == ["after clear"])
    assert [line.text for line in buffer.snapshot("survival")] == ["before clear", "after clear"]

    controller.show_server("creative")
    controller.show_server("survival")  # history replay must not bring back cleared lines
    qtbot.wait(50)
    assert recorder.texts() == ["after clear"]


def test_close_and_deselect_unsubscribe(qtbot: QtBot, buffer: ServerOutputBuffer) -> None:
    controller, recorder, bridge = console_for(buffer)
    controller.show_server("survival")
    assert subscriber_count(buffer) == 1

    controller.show_server(None)
    assert subscriber_count(buffer) == 0 and not bridge.attached

    controller.show_server("survival")
    controller.close()
    buffer.publish("survival", OutputStream.STDOUT, "after close")
    qtbot.wait(50)

    assert subscriber_count(buffer) == 0
    assert "after close" not in recorder.texts()


def test_selecting_same_server_again_keeps_console(qtbot: QtBot, buffer: ServerOutputBuffer) -> None:
    controller, recorder, bridge = console_for(buffer)
    controller.show_server("survival")
    generation = bridge.generation

    controller.show_server("survival")

    assert bridge.generation == generation
    assert recorder.clears == 1


def test_without_output_console_is_unavailable(qtbot: QtBot) -> None:
    controller = ConsoleController(None)
    recorder = Recorder(controller)

    controller.show_server("survival")
    controller.clear()

    assert not controller.available
    assert recorder.lines == []


# --- view -------------------------------------------------------------------------------


def test_view_appends_lines_formats_stderr_and_clears(qtbot: QtBot) -> None:
    view = ServerConsoleView(messages_for(), available=True)
    qtbot.addWidget(view)

    view.append_lines((ConsoleLine(1, False, "info line"), ConsoleLine(2, True, "error line")))

    assert view.plain_text() == "info line\nerror line"
    document = view.text.document()
    colors = [document.findBlockByNumber(n).begin().fragment().charFormat().foreground().color().name() for n in (0, 1)]
    assert colors == [theme.CONSOLE_TEXT, theme.CONSOLE_ERROR]
    view.clear()
    assert view.plain_text() == ""
    assert view.text.isReadOnly()


def test_view_follows_end_only_when_at_bottom(qtbot: QtBot) -> None:
    view = ServerConsoleView(messages_for(), available=True)
    qtbot.addWidget(view)
    view.resize(500, 200)
    view.show()
    view.append_lines(tuple(ConsoleLine(n, False, f"line {n}") for n in range(1, 200)))
    bar = view.text.verticalScrollBar()
    assert bar.value() == bar.maximum()

    bar.setValue(0)
    view.append_lines((ConsoleLine(200, False, "new"),))

    assert bar.value() == 0


def test_unavailable_view_explains_why(qtbot: QtBot) -> None:
    messages = messages_for()
    view = ServerConsoleView(messages, available=False)
    qtbot.addWidget(view)

    assert view.pages.currentWidget() is view.unavailable_label
    assert view.unavailable_label.text() == messages.text("console.unavailable")
    assert not view.clear_button.isEnabled()
