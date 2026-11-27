"""One queue for transient notifications: success, info, warning and error (M4-GUI-04).

Every message that used to flash in the status bar goes through
``NotificationCenter``. At most ``MAX_VISIBLE`` notifications show at once;
the rest wait in order and appear as shown ones are dismissed. Success and
info notifications dismiss themselves after a while, warnings later; errors
stay until the user dismisses them and offer their technical details. The same
message arriving again while it is still listed is counted, not repeated.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from PySide6.QtCore import QObject, QTimer, Signal

from mcserver.presentation.errors import UserMessage

TONES = ("success", "info", "notice", "error")
"""``notice`` is the warning tone (the same name the inline banners use)."""
MAX_VISIBLE = 3
MAX_KEPT = 50
"""Older waiting notifications are dropped beyond this many (never errors that are shown)."""
AUTO_DISMISS_MS: Mapping[str, int] = {"success": 6000, "info": 6000, "notice": 12000}
"""Errors are not in this table: they stay until dismissed."""


@dataclass(frozen=True, slots=True)
class Notification:
    """One notification; ``count`` tells how often the same message arrived."""

    notification_id: int
    message: UserMessage
    tone: str
    count: int = 1

    @property
    def has_details(self) -> bool:
        """Return whether a Details action is offered (errors with technical details)."""
        return self.tone == "error" and bool(self.message.details)


@dataclass(frozen=True, slots=True)
class NotificationsState:
    """What the notification stack shows."""

    visible: tuple[Notification, ...] = ()
    waiting: int = 0


class NotificationCenter(QObject):
    """Queue notifications, dismiss them on request or after their timeout."""

    changed = Signal(object)  # NotificationsState

    def __init__(self, parent: QObject | None = None, auto_dismiss_ms: Mapping[str, int] | None = None) -> None:
        """Use ``auto_dismiss_ms`` per tone (tests shorten it); tones not listed stay until dismissed."""
        super().__init__(parent)
        self._auto_dismiss = dict(AUTO_DISMISS_MS if auto_dismiss_ms is None else auto_dismiss_ms)
        self._items: list[Notification] = []
        self._timers: dict[int, QTimer] = {}
        self._next_id = 1

    @property
    def state(self) -> NotificationsState:
        """Return what is shown and how many wait."""
        return NotificationsState(tuple(self._items[:MAX_VISIBLE]), max(0, len(self._items) - MAX_VISIBLE))

    @property
    def all(self) -> tuple[Notification, ...]:
        """Return every listed notification, shown ones first."""
        return tuple(self._items)

    def notify(self, message: UserMessage, tone: str = "info") -> int:
        """Add ``message`` (or count it again when it is already listed); return its id."""
        if tone not in TONES:
            tone = "info"
        for index, item in enumerate(self._items):
            if item.message == message and item.tone == tone:
                self._items[index] = replace(item, count=item.count + 1)
                self._restart_timer(item.notification_id)
                self._publish()
                return item.notification_id
        notification = Notification(self._next_id, message, tone)
        self._next_id += 1
        self._items.append(notification)
        self._trim()
        self._publish()
        return notification.notification_id

    def dismiss(self, notification_id: int) -> None:
        """Remove one notification; the next waiting one appears."""
        before = len(self._items)
        self._items = [item for item in self._items if item.notification_id != notification_id]
        self._stop_timer(notification_id)
        if len(self._items) != before:
            self._publish()

    def dismiss_all(self) -> None:
        """Remove every notification."""
        if not self._items:
            return
        for notification_id in list(self._timers):
            self._stop_timer(notification_id)
        self._items.clear()
        self._publish()

    def hold(self, held: bool) -> None:
        """Pause auto-dismiss while the pointer rests on the notifications; resume with full time."""
        for timer in self._timers.values():
            if held:
                timer.stop()
            else:
                timer.start()

    def _trim(self) -> None:
        # Drop the oldest waiting ones first; shown notifications are what the user may be reading.
        while len(self._items) > MAX_KEPT:
            removed = self._items.pop(MAX_VISIBLE)
            self._stop_timer(removed.notification_id)

    def _publish(self) -> None:
        state = self.state
        for item in state.visible:
            if item.notification_id not in self._timers:
                self._start_timer(item)
        self.changed.emit(state)

    def _start_timer(self, item: Notification) -> None:
        timeout = self._auto_dismiss.get(item.tone)
        if timeout is None:
            return
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda notification_id=item.notification_id: self.dismiss(notification_id))
        self._timers[item.notification_id] = timer
        timer.start(timeout)

    def _restart_timer(self, notification_id: int) -> None:
        timer = self._timers.get(notification_id)
        if timer is not None:
            timer.start()

    def _stop_timer(self, notification_id: int) -> None:
        timer = self._timers.pop(notification_id, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()


__all__ = [
    "AUTO_DISMISS_MS",
    "MAX_VISIBLE",
    "TONES",
    "Notification",
    "NotificationCenter",
    "NotificationsState",
]
