"""How much RAM a server may use, picked with a slider in whole gigabytes (UX overhaul).

Nobody needs to know JVM arguments: the slider shows "4 GB", offers the common sizes
as one-click choices, and never goes past what this PC can spare for Minecraft.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from mcserver.presentation.i18n import Messages

DEFAULT_GB = 2
MIN_GB = 1
HARD_MAX_GB = 32
"""More than this is never useful for one Minecraft server and makes the slider hard to use."""
UNKNOWN_TOTAL_MB = 8 * 1024
"""Assumed when the PC's memory cannot be read."""
PRESETS_GB = (2, 4, 6, 8, 12, 16)


@dataclass(frozen=True, slots=True)
class MemoryLimits:
    """The slider's range for this PC."""

    total_gb: int
    maximum_gb: int
    default_gb: int


def memory_limits(total_mb: int | None) -> MemoryLimits:
    """Return the range for a PC with ``total_mb`` of RAM, keeping enough for Windows and other programs.

    Windows keeps the larger of 2 GB and a quarter of the RAM; the server gets the rest,
    in whole gigabytes, between 1 GB and 32 GB.
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


class MemorySlider(QWidget):
    """A labelled slider with quick choices; ``value_mb`` is what the server gets."""

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
        self.value_label = QLabel()
        self.value_label.setObjectName("memoryValue")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("memorySliderBar")
        self.slider.setRange(MIN_GB, maximum)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(2)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(1 if maximum <= 16 else 2)
        start = self.limits.default_gb if value_mb is None else max(MIN_GB, round(value_mb / 1024))
        self.slider.setValue(min(maximum, start))
        self.slider.valueChanged.connect(self._on_slider)
        self.slider.setAccessibleName(messages.text("memory.label"))
        self.minimum_label = QLabel(messages.text("memory.gb", value=MIN_GB))
        self.minimum_label.setObjectName("fieldHint")
        self.range_label = QLabel(
            messages.text("memory.recommended", maximum=self.limits.maximum_gb, total=self.limits.total_gb)
        )
        self.range_label.setObjectName("fieldHint")
        self.range_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.presets = QButtonGroup(self)
        self.presets.setExclusive(False)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for gigabytes in PRESETS_GB:
            if gigabytes > maximum:
                continue
            chip = QPushButton(messages.text("memory.gb", value=gigabytes))
            chip.setObjectName("chipButton")
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setAccessibleName(messages.text("memory.preset", value=gigabytes))
            chip.clicked.connect(lambda _checked=False, value=gigabytes: self.slider.setValue(value))
            self.presets.addButton(chip, gigabytes)
            preset_row.addWidget(chip)
        preset_row.addStretch(1)
        ends = QHBoxLayout()
        ends.addWidget(self.minimum_label)
        ends.addStretch(1)
        ends.addWidget(self.range_label)
        top = QHBoxLayout()
        top.addWidget(self.slider, 1)
        top.addSpacing(12)
        top.addWidget(self.value_label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(top)
        layout.addLayout(ends)
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


__all__ = ["DEFAULT_GB", "MemoryLimits", "MemorySlider", "format_gb", "memory_limits"]
