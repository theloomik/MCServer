"""Notifications floating at the bottom right of the content area (M4-GUI-04)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from mcserver.presentation import icons, theme
from mcserver.presentation.errors import render_message
from mcserver.presentation.i18n import Messages
from mcserver.presentation.notifications import Notification, NotificationsState
from mcserver.presentation.views.widgets import icon_button, repolish

WIDTH = 380
MARGIN = 16
_ICONS = {"error": "alert", "notice": "alert", "success": "check", "info": "info"}


class Toast(QFrame):
    """One notification: tone icon, text, Details (errors) and a close button."""

    dismiss_requested = Signal(int)
    details_requested = Signal(object)  # UserMessage

    def __init__(self, notification: Notification, messages: Messages) -> None:
        """Render ``notification``."""
        super().__init__()
        self.setObjectName("toast")
        self.notification = notification
        self.setProperty("tone", notification.tone)
        text = render_message(messages, notification.message)
        if notification.count > 1:
            text = messages.text("notifications.repeated", text=text, count=notification.count)
        self.icon = QLabel()
        self.icon.setFixedSize(16, 16)
        foreground = theme.TONE_COLORS.get(notification.tone, theme.TONE_COLORS["info"])[2]
        self.icon.setPixmap(icons.pixmap(_ICONS.get(notification.tone, "info"), foreground, 16))
        self.text = QLabel(text)
        self.text.setObjectName("toastText")
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_button = QPushButton(messages.text("notifications.details"))
        self.details_button.setObjectName("linkButton")
        self.details_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.details_button.setVisible(notification.has_details)
        self.details_button.clicked.connect(lambda: self.details_requested.emit(notification.message))
        self.close_button = icon_button("close", messages.text("notifications.dismiss"))
        self.close_button.setAccessibleName(messages.text("notifications.dismiss"))
        self.close_button.clicked.connect(lambda: self.dismiss_requested.emit(notification.notification_id))
        self.setAccessibleName(text)
        actions = QVBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(2)
        actions.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignRight)
        actions.addStretch(1)
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(4)
        body.addWidget(self.text)
        body.addWidget(self.details_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 6, 10)
        layout.setSpacing(10)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(body, 1)
        layout.addLayout(actions)
        repolish(self)


class ToastStack(QWidget):
    """Shows ``NotificationsState`` over a host widget, newest at the bottom, with a 'more' row."""

    dismiss_requested = Signal(int)
    dismiss_all_requested = Signal()
    details_requested = Signal(object)  # UserMessage
    hover_changed = Signal(bool)

    def __init__(self, messages: Messages, host: QWidget) -> None:
        """Float over ``host`` (a child of it, kept at its bottom right)."""
        super().__init__(host)
        self.setObjectName("toastStack")
        self._messages = messages
        self._host = host
        self.toasts: list[Toast] = []
        self.more_label = QLabel()
        self.more_label.setObjectName("toastMore")
        self.dismiss_all_button = QPushButton(messages.text("notifications.dismiss_all"))
        self.dismiss_all_button.setObjectName("linkButton")
        self.dismiss_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dismiss_all_button.clicked.connect(self.dismiss_all_requested)
        self.more_row = QFrame()
        self.more_row.setObjectName("toastMoreRow")
        more = QHBoxLayout(self.more_row)
        more.setContentsMargins(12, 6, 12, 6)
        more.addWidget(self.more_label, 1)
        more.addWidget(self.dismiss_all_button)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.addWidget(self.more_row)
        self.setFixedWidth(WIDTH)
        host.installEventFilter(self)
        self.hide()

    def show_state(self, state: NotificationsState) -> None:
        """Rebuild the toasts for ``state``."""
        for toast in self.toasts:
            self._layout.removeWidget(toast)
            toast.hide()  # it would paint until deleteLater runs
            toast.deleteLater()
        self.toasts = []
        for notification in state.visible:
            toast = Toast(notification, self._messages)
            toast.dismiss_requested.connect(self.dismiss_requested)
            toast.details_requested.connect(self.details_requested)
            self._layout.addWidget(toast)
            toast.show()  # children added to a visible parent are otherwise shown only on the next event loop turn
            self.toasts.append(toast)
        hidden = state.waiting
        self.more_row.setVisible(hidden > 0 or len(state.visible) > 1)
        self.more_label.setText(self._messages.plural("notifications.more", hidden) if hidden else "")
        self.setVisible(bool(state.visible))
        self._place()

    def texts(self) -> list[str]:
        """Return the shown texts (for tests and accessibility checks)."""
        return [toast.text.text() for toast in self.toasts]

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        """Follow the host's size."""
        if watched is self._host and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self._place()
        return False

    def event(self, event: QEvent) -> bool:
        """Refit when the toasts' layout changes (text wraps differently, a toast is removed)."""
        if event.type() == QEvent.Type.LayoutRequest:
            self._place()
        return super().event(event)

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802 (Qt override)
        """Keep the notifications while the pointer is on them."""
        self.hover_changed.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802 (Qt override)
        """Let them dismiss themselves again."""
        self.hover_changed.emit(False)
        super().leaveEvent(event)

    def _place(self) -> None:
        if self.isHidden():
            return
        layout = self._layout
        height = layout.totalHeightForWidth(WIDTH) if layout.hasHeightForWidth() else layout.totalSizeHint().height()
        host = self._host.rect()
        self.setGeometry(host.right() - WIDTH - MARGIN + 1, host.bottom() - height - MARGIN + 1, WIDTH, height)
        self.raise_()


__all__ = ["Toast", "ToastStack"]
