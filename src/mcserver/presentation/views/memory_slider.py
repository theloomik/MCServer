"""How much RAM a server may use, picked in whole gigabytes on a slider with marks (UX overhaul).

Nobody needs to know JVM arguments: the slider moves between 1 GB, 2 GB, 3 GB … only,
every step has a mark below the bar, the chosen amount is shown large, and the range
never goes past what this PC can spare for Minecraft.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

from mcserver.presentation import theme
from mcserver.presentation.i18n import Messages

DEFAULT_GB = 2
MIN_GB = 1
HARD_MAX_GB = 32
"""More than this is never useful for one Minecraft server and makes the slider hard to use."""
UNKNOWN_TOTAL_MB = 8 * 1024
"""Assumed when the PC's memory cannot be read."""
PRESETS_GB = (2, 4, 8, 16)
"""One-click choices; only those within the range are shown, and only when the range is wide."""
_LABEL_SPACING_PX = 34
"""Numbers under the marks are skipped (every 2nd, 4th …) when they would come closer than this."""


@dataclass(frozen=True, slots=True)
class MemoryLimits:
    """The slider's range for this PC."""

    total_gb: int
    maximum_gb: int
    default_gb: int


def memory_limits(total_mb: int | None) -> MemoryLimits:
    """Return the range for a PC with ``total_mb`` of RAM, keeping enough for Windows and other programs.

    Windows keeps the larger of 2 GB and a quarter of the RAM; the server gets the rest,
    in whole gigabytes, between 1 GB and 32 GB. The default is 2 GB, or less when the PC
    cannot spare that much.
    """
    total = total_mb if total_mb and total_mb > 0 else UNKNOWN_TOTAL_MB
    total_gb = max(1, round(total / 1024))
    reserve_gb = max(2.0, total_gb * 0.25)
    maximum = int(max(MIN_GB, min(HARD_MAX_GB, total_gb - reserve_gb)))
    return MemoryLimits(total_gb, maximum, min(DEFAULT_GB, maximum))


def format_gb(megabytes: int) -> str:
    """Return ``megabytes`` as gigabytes without a needless ``.0`` (``4``, ``4.5``)."""
    value = megabytes / 1024
    return f"{value:.0f}" if value == int(value) else f"{value:.1f}"


class SnapSlider(QSlider):
    """A horizontal slider that only takes whole steps; clicking the bar jumps to the nearest step."""

    def __init__(self) -> None:
        super().__init__(Qt.Orientation.Horizontal)
        self.setObjectName("memorySliderBar")
        self.setSingleStep(1)
        self.setPageStep(1)
        self.setTracking(True)

    def handle_rect(self) -> QRect:
        """Return where the handle is drawn now."""
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        return self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self
        )

    def position_of(self, value: int) -> float:
        """Return the x coordinate of the handle's centre when it shows ``value``."""
        handle = self.handle_rect().width() or 18
        span = max(1, self.maximum() - self.minimum())
        usable = self.width() - handle
        return handle / 2 + usable * (value - self.minimum()) / span

    def value_at(self, x: float) -> int:
        """Return the step nearest to the x coordinate ``x``."""
        handle = self.handle_rect().width() or 18
        usable = max(1, self.width() - handle)
        fraction = min(1.0, max(0.0, (x - handle / 2) / usable))
        return round(self.minimum() + fraction * (self.maximum() - self.minimum()))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        """A click beside the handle moves it there (to the nearest step), not one page further."""
        if event.button() == Qt.MouseButton.LeftButton and not self.handle_rect().contains(event.position().toPoint()):
            self.setValue(self.value_at(event.position().x()))
            event.accept()
        super().mousePressEvent(event)


class TickScale(QWidget):
    """Marks under the slider, one per step, with the amounts written below (thinned when crowded)."""

    def __init__(self, slider: SnapSlider) -> None:
        super().__init__()
        self.slider = slider
        self.setObjectName("memoryTicks")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self.fontMetrics().height() + 10)
        slider.rangeChanged.connect(lambda _low, _high: self.update())
        slider.valueChanged.connect(lambda _value: self.update())

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        """As wide as the slider wants to be."""
        return QSize(self.slider.sizeHint().width(), self.height())

    def label_step(self) -> int:
        """Return every how many marks a number is written (1, 2, 4 …) so the numbers never touch."""
        count = max(1, self.slider.maximum() - self.slider.minimum())
        spacing = max(1.0, (self.width() - 18) / count)
        step = 1
        while spacing * step < _LABEL_SPACING_PX and step < count:
            step *= 2
        return step

    def labelled_values(self) -> list[int]:
        """Return the amounts that get a number: every ``label_step``-th, and always the minimum and maximum."""
        low, high = self.slider.minimum(), self.slider.maximum()
        step = self.label_step()
        values = [value for value in range(low, high + 1) if (value - low) % step == 0]
        if values[-1] != high:
            if len(values) > 1 and (high - values[-1]) * (self.width() / max(1, high - low)) < _LABEL_SPACING_PX:
                values.pop()  # too close to the maximum, which always gets its number
            values.append(high)
        return values

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt override)
        """Draw one mark per step; the chosen one is longer and in the accent colour."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        offset = (
            self.slider.mapTo(self.window(), self.slider.rect().topLeft()).x()
            - self.mapTo(self.window(), self.rect().topLeft()).x()
        )
        labelled = set(self.labelled_values())
        metrics = self.fontMetrics()
        for value in range(self.slider.minimum(), self.slider.maximum() + 1):
            x = offset + self.slider.position_of(value)
            chosen = value == self.slider.value()
            color = QColor(theme.ACCENT if chosen else theme.TEXT_MUTED)
            painter.setPen(QPen(color, 1.5 if chosen else 1))
            painter.drawLine(int(x), 0, int(x), 6 if chosen or value in labelled else 3)
            if value in labelled:
                painter.setPen(QColor(theme.TEXT if chosen else theme.TEXT_MUTED))
                text = str(value)
                width = metrics.horizontalAdvance(text)
                left = min(max(0, int(x - width / 2)), self.width() - width)
                painter.drawText(left, 8 + metrics.ascent(), text)
        painter.end()


class MemorySlider(QWidget):
    """The memory picker: the chosen amount, the slider with marks, a short recommendation, quick choices."""

    changed = Signal(int)  # megabytes

    def __init__(self, messages: Messages, total_mb: int | None, value_mb: int | None = None) -> None:
        """Offer this PC's range; ``value_mb`` (an existing server's) is kept until the user moves the slider."""
        super().__init__()
        self.setObjectName("memorySlider")
        self._messages = messages
        self.limits = memory_limits(total_mb)
        self._original_mb = value_mb
        maximum = self.limits.maximum_gb
        if value_mb is not None:
            maximum = max(maximum, min(HARD_MAX_GB * 4, round(value_mb / 1024)))  # never hide the current value
        self.slider = SnapSlider()
        self.slider.setRange(MIN_GB, maximum)
        start = self.limits.default_gb if value_mb is None else max(MIN_GB, round(value_mb / 1024))
        self.slider.setValue(min(maximum, start))
        self.slider.valueChanged.connect(self._on_slider)
        self.slider.setAccessibleName(messages.text("memory.label"))
        self.value_label = QLabel()
        self.value_label.setObjectName("memoryValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.ticks = TickScale(self.slider)
        self.range_label = QLabel()
        self.range_label.setObjectName("fieldHint")
        self.range_label.setWordWrap(True)
        self.presets = QButtonGroup(self)
        self.presets.setExclusive(False)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        choices = [gigabytes for gigabytes in PRESETS_GB if gigabytes <= maximum]
        if maximum >= 6 and len(choices) >= 2:  # with a short range the marks alone are enough
            for gigabytes in choices:
                chip = QPushButton(messages.text("memory.gb", value=gigabytes))
                chip.setObjectName("chipButton")
                chip.setCheckable(True)
                chip.setCursor(Qt.CursorShape.PointingHandCursor)
                chip.setAccessibleName(messages.text("memory.preset", value=gigabytes))
                chip.clicked.connect(lambda _checked=False, value=gigabytes: self.slider.setValue(value))
                self.presets.addButton(chip, gigabytes)
                preset_row.addWidget(chip)
            preset_row.addStretch(1)
        bar = QVBoxLayout()
        bar.setSpacing(2)
        bar.addWidget(self.slider)
        bar.addWidget(self.ticks)
        top = QHBoxLayout()
        top.setSpacing(16)
        top.addLayout(bar, 1)
        top.addWidget(self.value_label, 0, Qt.AlignmentFlag.AlignTop)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(top)
        layout.addWidget(self.range_label)
        if self.presets.buttons():
            layout.addLayout(preset_row)
        self._show()

    def value_mb(self) -> int:
        """Return the memory to give the server, in megabytes."""
        if self._original_mb is not None and round(self._original_mb / 1024) == self.slider.value():
            return self._original_mb  # an existing value like 4608 MB stays exact until the slider moves
        return self.slider.value() * 1024

    def _on_slider(self, _value: int) -> None:
        self._show()
        self.changed.emit(self.value_mb())

    def _show(self) -> None:
        megabytes = self.value_mb()
        text = self._messages.text("memory.gb", value=format_gb(megabytes))
        self.value_label.setText(text)
        self.slider.setAccessibleDescription(text)
        self.slider.setToolTip(text)
        for chip in self.presets.buttons():
            chip.setChecked(self.presets.id(chip) * 1024 == megabytes)
        over = megabytes > self.limits.maximum_gb * 1024
        self.value_label.setProperty("warning", over)
        self.range_label.setText(
            self._messages.text("memory.over", maximum=self.limits.maximum_gb)
            if over
            else self._messages.text("memory.recommended", maximum=self.limits.maximum_gb, total=self.limits.total_gb)
        )
        style = self.value_label.style()
        style.unpolish(self.value_label)
        style.polish(self.value_label)


__all__ = ["DEFAULT_GB", "MemoryLimits", "MemorySlider", "SnapSlider", "TickScale", "format_gb", "memory_limits"]
