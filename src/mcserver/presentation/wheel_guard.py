"""The mouse wheel scrolls pages, not the value under the pointer (UX overhaul).

Qt changes a spin box, combo box or slider when the wheel turns over it, even while
the user only wants to scroll the page past it. This filter gives the wheel to the
page instead unless the control already has the keyboard focus, so values change only
on purpose: by clicking, typing, the arrow keys, or the wheel after clicking in.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QSlider,
    QWidget,
)

_GUARDED = (QAbstractSpinBox, QComboBox, QSlider)


def _control(watched: QObject) -> QWidget | None:
    """Return the guarded control ``watched`` belongs to (a spin box's line edit counts as the spin box)."""
    if isinstance(watched, _GUARDED):
        return watched
    if isinstance(watched, QLineEdit) and isinstance(watched.parentWidget(), _GUARDED):
        return watched.parentWidget()
    return None


def _scroll_area(widget: QWidget) -> QAbstractScrollArea | None:
    """Return the nearest scrolling area around ``widget`` (the page the wheel should move)."""
    current = widget.parentWidget()
    while current is not None:
        if isinstance(current, QAbstractScrollArea) and not isinstance(current, QAbstractItemView):
            return current
        current = current.parentWidget()
    return None


class WheelGuard(QObject):
    """Application event filter; see the module docstring."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        """Pass a wheel turn over an unfocused control on to the page behind it."""
        if event.type() == QEvent.Type.Wheel:
            control = _control(watched)
            if control is not None and not control.hasFocus():
                area = _scroll_area(control)
                if area is not None:
                    QApplication.sendEvent(area.viewport(), event)
                return True
        elif event.type() == QEvent.Type.Polish:
            control = _control(watched)
            if control is not None and control.focusPolicy() == Qt.FocusPolicy.WheelFocus:
                control.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # turning the wheel never takes the focus
        return False


_installed: dict[int, WheelGuard] = {}


def install_wheel_guard(app: QApplication | None = None) -> WheelGuard | None:
    """Install the guard on ``app`` (the running application by default) once; return it."""
    application = app or QApplication.instance()
    if not isinstance(application, QApplication):
        return None
    guard = _installed.get(id(application))
    if guard is None:
        guard = WheelGuard(application)
        application.installEventFilter(guard)
        _installed[id(application)] = guard
    return guard


__all__ = ["WheelGuard", "install_wheel_guard"]
