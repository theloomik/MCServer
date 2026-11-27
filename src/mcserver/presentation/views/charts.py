"""A small history chart for the resources card (M4-GUI-06): line and soft area, newest sample on the right."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from mcserver.presentation import theme

CHART_HEIGHT = 40


class Sparkline(QWidget):
    """Draw up to ``capacity`` values between 0 and ``maximum``; the time axis is fixed, so the line moves left."""

    def __init__(self, color_token: str, capacity: int, parent: QWidget | None = None) -> None:
        """Use the theme colour named ``color_token`` (read when painting, so it follows the theme)."""
        super().__init__(parent)
        self.setObjectName("sparkline")
        self.color_token = color_token
        self.capacity = max(2, capacity)
        self.values: tuple[float, ...] = ()
        self.maximum = 1.0
        self.active = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(CHART_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        """Prefer a wide, low chart."""
        return QSize(200, CHART_HEIGHT)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        """Shrink with the card."""
        return QSize(60, CHART_HEIGHT)

    def set_series(self, values: Sequence[float], maximum: float, *, active: bool, description: str) -> None:
        """Show ``values`` (oldest first) on a 0–``maximum`` scale; ``active`` is false for a stopped server."""
        self.values = tuple(max(0.0, value) for value in values[-self.capacity :])
        self.maximum = max(maximum, max(self.values, default=0.0), 1e-9)
        self.active = active
        self.setAccessibleDescription(description)
        self.setToolTip(description)
        self.update()

    def color(self) -> QColor:
        """Return the line colour: the metric's colour while running, muted afterwards."""
        return QColor(getattr(theme, self.color_token) if self.active else theme.TEXT_MUTED)

    def points(self) -> list[QPointF]:
        """Return where each value is drawn (empty when there is nothing to draw)."""
        if len(self.values) < 2:
            return []
        area = QRectF(self.rect()).adjusted(1, 2, -1, -2)
        step = area.width() / (self.capacity - 1)
        start = area.right() - step * (len(self.values) - 1)
        return [
            QPointF(start + step * index, area.bottom() - area.height() * min(1.0, value / self.maximum))
            for index, value in enumerate(self.values)
        ]

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt override)
        """Draw the baseline, then the filled area and the line."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bottom = self.height() - 1.5
        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.drawLine(QPointF(0, bottom), QPointF(self.width(), bottom))
        points = self.points()
        if points:
            color = self.color()
            line = QPainterPath(points[0])
            for point in points[1:]:
                line.lineTo(point)
            area = QPainterPath(line)
            area.lineTo(points[-1].x(), bottom)
            area.lineTo(points[0].x(), bottom)
            area.closeSubpath()
            fill = QColor(color)
            fill.setAlpha(46)
            painter.fillPath(area, fill)
            painter.setPen(QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(line)
        painter.end()


__all__ = ["CHART_HEIGHT", "Sparkline"]
