"""Building blocks from the M4 design: buttons by kind, cards, panel bars, banner, metric row."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mcserver.presentation import icons, theme

BUTTON_KINDS = ("primary", "secondary", "ghost", "danger")
_ICON_COLORS = {
    "primary": theme.TEXT_ON_ACCENT,
    "secondary": theme.TEXT,
    "ghost": theme.TEXT_SECONDARY,
    "danger": theme.DANGER_TEXT,
}


def repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property change."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def set_icon(button: QPushButton, name: str | None, kind: str = "secondary") -> None:
    """Show icon ``name`` on ``button`` in the colour of its kind (``None`` removes it)."""
    if name is None:
        button.setIcon(QIcon())
        return
    button.setIcon(icons.icon(name, _ICON_COLORS.get(kind, theme.TEXT_SECONDARY)))
    button.setIconSize(QSize(16, 16))


def button(
    text: str, kind: str = "secondary", icon_name: str | None = None, object_name: str | None = None
) -> QPushButton:
    """Return a 32 px button of ``kind`` (primary, secondary, ghost, danger) with an optional icon."""
    result = QPushButton(text)
    result.setObjectName(object_name or f"{kind}Button")
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    set_icon(result, icon_name, kind)
    return result


def icon_button(icon_name: str, tooltip: str, object_name: str = "iconButton") -> QPushButton:
    """Return a borderless square button showing only an icon (the text is in the tooltip)."""
    result = QPushButton()
    result.setObjectName(object_name)
    result.setToolTip(tooltip)
    result.setAccessibleName(tooltip)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    result.setIcon(icons.icon(icon_name, theme.TEXT_SECONDARY))
    result.setIconSize(QSize(16, 16))
    return result


def icon_label(icon_name: str, color: str | None = None, size: int = 16) -> QLabel:
    """Return a label showing an icon."""
    label = QLabel()
    label.setPixmap(icons.pixmap(icon_name, color, size))
    label.setFixedSize(size, size)
    return label


def card(object_name: str | None = None) -> QFrame:
    """Return a card surface (rounded, bordered)."""
    frame = QFrame()
    frame.setProperty("card", True)
    if object_name:
        frame.setObjectName(object_name)
    return frame


def panel_bar(position: str = "top") -> tuple[QFrame, QHBoxLayout]:
    """Return a toolbar strip for a panel card: ``top`` (border below), ``bottom`` (border above) or ``band``."""
    frame = QFrame()
    frame.setProperty("panelBar", position)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(14, 8, 8, 8)
    layout.setSpacing(8)
    return frame, layout


def caption(text: str) -> QLabel:
    """Return an overline caption (upper case, muted)."""
    label = QLabel(text.upper())
    label.setObjectName("sectionCaption")
    return label


class Banner(QFrame):
    """Inline message with a tone (error, notice, success, info), an icon and an optional action."""

    _ICONS = {"error": "alert", "notice": "alert", "success": "check", "info": "info"}

    def __init__(self, action_text: str = "") -> None:
        """Build a hidden banner; ``action_text`` labels the action button."""
        super().__init__()
        self.setObjectName("banner")
        self.icon = QLabel()
        self.icon.setFixedSize(16, 16)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.action = QPushButton(action_text)
        self.action.setObjectName("linkButton")
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.hide()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 10, 9)
        layout.setSpacing(10)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.text, 1)
        layout.addWidget(self.action, 0, Qt.AlignmentFlag.AlignTop)
        self.hide()

    def show_message(self, text: str, tone: str, show_action: bool = False) -> None:
        """Show ``text`` in ``tone``; the action button is shown when asked."""
        foreground = theme.TONE_COLORS.get(tone, theme.TONE_COLORS["info"])[2]
        self.icon.setPixmap(icons.pixmap(self._ICONS.get(tone, "info"), foreground, 16))
        self.text.setText(text)
        self.setProperty("tone", tone)
        repolish(self)
        self.action.setVisible(show_action)
        self.text.show()
        self.show()

    def clear(self) -> None:
        """Hide the banner and its text."""
        self.text.hide()
        self.hide()


class WrapRow(QWidget):
    """Two groups on one line when they fit, the second below the first otherwise (narrow or scaled windows)."""

    def __init__(self, first: QWidget, second: QWidget, spacing: int = 12, *, fill: bool = False) -> None:
        """Lay out ``first`` and ``second``: apart (or, with ``fill``, sharing the width), or one below the other."""
        super().__init__()
        self.first = first
        self.second = second
        self.row = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(spacing)
        self.row.addWidget(first, 1 if fill else 0)
        if not fill:
            self.row.addStretch(1)
        self.row.addWidget(second, 1 if fill else 0)

    @property
    def wrapped(self) -> bool:
        """Return whether the second group is below the first."""
        return self.row.direction() is QBoxLayout.Direction.TopToBottom

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        """Need only the wider group, so the window can be narrow."""
        first, second = self.first.minimumSizeHint(), self.second.minimumSizeHint()
        return QSize(max(first.width(), second.width()), first.height() + second.height() + self.row.spacing())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        """Put both groups on one line only when they fit."""
        needed = self.first.sizeHint().width() + self.second.sizeHint().width() + self.row.spacing()
        wrap = event.size().width() < needed
        if wrap != self.wrapped:
            self.row.setDirection(QBoxLayout.Direction.TopToBottom if wrap else QBoxLayout.Direction.LeftToRight)
        super().resizeEvent(event)


class MetricRow(QWidget):
    """Label and value on one line, with an optional thin bar below (CPU, memory)."""

    def __init__(self, label: str, value: str, with_bar: bool = False) -> None:
        """Build the row."""
        super().__init__()
        self.label = QLabel(label)
        self.label.setObjectName("fieldLabel")
        self.value = QLabel(value)
        self.value.setObjectName("metricValue")
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.label, 1)
        top.addWidget(self.value)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(top)
        self.bar: QProgressBar | None = None
        if with_bar:
            self.bar = QProgressBar()
            self.bar.setRange(0, 1000)
            self.bar.setValue(0)
            self.bar.setTextVisible(False)
            self.bar.setFixedHeight(4)
            layout.addWidget(self.bar)

    def set_fraction(self, fraction: float | None) -> None:
        """Fill the bar to ``fraction`` (0–1); ``None`` empties it."""
        if self.bar is not None:
            self.bar.setValue(0 if fraction is None else max(0, min(1000, round(fraction * 1000))))
