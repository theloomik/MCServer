"""The notification queue and its toasts (M4-GUI-04)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from mcserver.presentation.errors import UserMessage, describe_error
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.notifications import MAX_KEPT, MAX_VISIBLE, NotificationCenter
from mcserver.presentation.views.toasts import ToastStack

MESSAGES = messages_for("en")
SAVED = UserMessage("console.saved", {"path": "a.log"})


def center(qtbot: QtBot, **timeouts: int) -> NotificationCenter:
    return NotificationCenter(auto_dismiss_ms=timeouts)


def test_more_than_three_wait_in_order_and_appear_when_one_is_dismissed(qtbot: QtBot) -> None:
    notifications = center(qtbot)
    ids = [notifications.notify(UserMessage("console.saved", {"path": f"{n}.log"}), "success") for n in range(5)]

    state = notifications.state
    assert [item.notification_id for item in state.visible] == ids[:MAX_VISIBLE] and state.waiting == 2

    notifications.dismiss(ids[1])
    assert [item.notification_id for item in notifications.state.visible] == [ids[0], ids[2], ids[3]]
    notifications.dismiss_all()
    assert notifications.state.visible == () and notifications.state.waiting == 0


def test_the_same_message_is_counted_not_repeated(qtbot: QtBot) -> None:
    notifications = center(qtbot)
    first = notifications.notify(SAVED, "success")
    again = notifications.notify(SAVED, "success")
    other_tone = notifications.notify(SAVED, "error")

    assert first == again != other_tone
    assert [item.count for item in notifications.all] == [2, 1]


def test_success_dismisses_itself_but_errors_stay(qtbot: QtBot) -> None:
    notifications = center(qtbot, success=50)
    notifications.notify(SAVED, "success")
    error = notifications.notify(describe_error(OSError("disk full")), "error")

    qtbot.waitUntil(lambda: len(notifications.all) == 1, timeout=2000)
    assert notifications.all[0].notification_id == error and notifications.all[0].has_details


def test_holding_pauses_auto_dismiss(qtbot: QtBot) -> None:
    notifications = center(qtbot, success=80)
    notifications.notify(SAVED, "success")
    notifications.hold(True)
    qtbot.wait(200)
    assert len(notifications.all) == 1
    notifications.hold(False)
    qtbot.waitUntil(lambda: not notifications.all, timeout=2000)


def test_a_waiting_notification_starts_its_timer_only_when_shown(qtbot: QtBot) -> None:
    notifications = center(qtbot, success=80)
    for n in range(MAX_VISIBLE):
        notifications.notify(UserMessage("dashboard.open_folder_failed", {"path": str(n)}), "error")
    waiting = notifications.notify(SAVED, "success")
    qtbot.wait(200)
    assert waiting in {item.notification_id for item in notifications.all}  # not shown yet, so not expired

    notifications.dismiss(notifications.all[0].notification_id)
    qtbot.waitUntil(lambda: waiting not in {item.notification_id for item in notifications.all}, timeout=2000)


def test_old_waiting_notifications_are_dropped_beyond_the_limit(qtbot: QtBot) -> None:
    notifications = center(qtbot)
    ids = [notifications.notify(UserMessage("console.saved", {"path": str(n)}), "info") for n in range(MAX_KEPT + 5)]

    kept = [item.notification_id for item in notifications.all]
    assert len(kept) == MAX_KEPT
    assert kept[:MAX_VISIBLE] == ids[:MAX_VISIBLE]  # what the user may be reading stays
    assert kept[-1] == ids[-1]


def test_toasts_render_text_details_dismiss_and_the_more_row(qtbot: QtBot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(900, 600)
    host.show()
    notifications = NotificationCenter(host, auto_dismiss_ms={})
    stack = ToastStack(MESSAGES, host)
    notifications.changed.connect(stack.show_state)
    stack.dismiss_requested.connect(notifications.dismiss)
    stack.dismiss_all_requested.connect(notifications.dismiss_all)
    details: list[UserMessage] = []
    stack.details_requested.connect(details.append)

    error = describe_error(OSError("disk full"))
    notifications.notify(error, "error")
    notifications.notify(SAVED, "success")
    notifications.notify(SAVED, "success")
    for n in range(3):
        notifications.notify(UserMessage("console.saved", {"path": str(n)}), "info")

    assert stack.isVisible() and len(stack.toasts) == MAX_VISIBLE
    saved_text = MESSAGES.text("console.saved", path="a.log")
    assert MESSAGES.text("notifications.repeated", text=saved_text, count=2) in stack.texts()
    assert stack.more_row.isVisible() and stack.more_label.text() == MESSAGES.plural("notifications.more", 2)
    assert stack.geometry().right() < host.width() and stack.geometry().bottom() < host.height()

    error_toast, saved_toast = stack.toasts[0], stack.toasts[1]
    assert not error_toast.details_button.isHidden() and saved_toast.details_button.isHidden()
    error_toast.details_button.click()
    assert details == [error]

    stack.toasts[0].close_button.click()
    assert len(notifications.all) == 4
    stack.dismiss_all_button.click()
    assert not stack.isVisible() and notifications.all == ()


def test_window_routes_messages_into_notifications(qtbot: QtBot, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from test_m2_gui import Setup

    setup = Setup(qtbot, tmp_path)
    window = setup.window
    window.notify(UserMessage("dashboard.no_logs"), "notice")
    window._show_error_in_status_bar(OSError("boom"))  # type: ignore[attr-defined]

    assert MESSAGES.text("dashboard.no_logs") in window.notification_texts()
    tones = [item.tone for item in window.notifications.all]
    assert tones == ["notice", "error"]
    assert not window.toast_stack.toasts[1].details_button.isHidden()
