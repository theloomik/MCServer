"""The shared progress panel and cancel in the backups and worlds controllers (M4-GUI-05)."""

from __future__ import annotations

from threading import Event

from pytestqt.qtbot import QtBot

from mcserver.application.backups import BackupInfo, BackupKind
from mcserver.application.progress import CancelToken, OperationCancelled, Progress, Stage
from mcserver.presentation.controllers.backups import BackupsController
from mcserver.presentation.errors import describe_error, error_tone
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.views.backups_view import BackupsView
from mcserver.presentation.views.progress_panel import ProgressPanel
from mcserver.presentation.workers import BackgroundRunner

MESSAGES = messages_for("en")


def test_panel_shows_stage_and_percent_then_cancelling(qtbot: QtBot) -> None:
    panel = ProgressPanel(MESSAGES)
    qtbot.addWidget(panel)
    cancelled: list[bool] = []
    panel.cancel_requested.connect(lambda: cancelled.append(True))

    panel.start()
    assert panel.running and panel.bar.maximum() == 0  # busy until the first report
    panel.show_progress(Progress(Stage.ARCHIVING, 25, 100))
    assert panel.stage_label.text() == MESSAGES.text("progress.stage.archiving")
    assert panel.percent_label.text() == "25%" and panel.bar.value() == 250
    panel.show_progress(Progress(Stage.SAVING_WORLD))
    assert panel.bar.maximum() == 0 and panel.percent_label.text() == ""

    panel.cancel_button.click()
    assert cancelled == [True] and not panel.cancel_button.isEnabled()
    assert panel.stage_label.text() == MESSAGES.text("progress.cancelling")
    panel.show_progress(Progress(Stage.ARCHIVING, 50, 100))
    assert panel.stage_label.text() == MESSAGES.text("progress.cancelling")  # stays until finished

    panel.finish()
    assert not panel.running


def test_every_stage_has_text_in_both_languages() -> None:
    for language in ("en", "uk"):
        messages = messages_for(language)
        for stage in Stage:
            key = f"progress.stage.{stage.value}"
            assert messages.text(key) != key


def test_cancelled_is_a_notice_not_an_error() -> None:
    error = OperationCancelled()
    assert describe_error(error).key == "progress.cancelled"
    assert error_tone(error) == "notice" and error_tone(RuntimeError()) == "error"


class SlowBackups:
    """Creates a backup only after the test releases it; honours cancel like the real service."""

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()

    def list(self, server_id: str) -> tuple[BackupInfo, ...]:
        return ()

    def create(self, server_id, note="", progress=None, kind=BackupKind.MANUAL, cancel=None):  # type: ignore[no-untyped-def]
        progress(Progress(Stage.ARCHIVING, 1, 4))
        self.started.set()
        self.release.wait(5)
        assert isinstance(cancel, CancelToken)
        cancel.check()
        return BackupInfo("id", server_id, "2026-11-24T10:00:00+00:00", 1, kind)


def test_cancel_from_the_view_stops_the_backup_and_shows_a_notice(qtbot: QtBot) -> None:
    service = SlowBackups()
    controller = BackupsController(service, BackgroundRunner())  # type: ignore[arg-type]
    view = BackupsView(MESSAGES)
    qtbot.addWidget(view)
    controller.state_changed.connect(view.show_state)
    controller.progress.connect(view.show_progress)
    view.cancel_requested.connect(controller.cancel)
    controller.show_server("survival")

    controller.create("")
    assert service.started.wait(5)
    qtbot.waitUntil(lambda: view.progress.percent_label.text() == "25%")
    assert view.progress.running and not view.progress.cancel_button.isHidden()

    view.progress.cancel_button.click()
    assert controller.state.cancelling
    service.release.set()
    qtbot.waitUntil(lambda: not controller.busy)

    assert controller.state.message is not None and controller.state.message.key == "progress.cancelled"
    assert controller.state.tone == "notice"
    assert not view.progress.running
