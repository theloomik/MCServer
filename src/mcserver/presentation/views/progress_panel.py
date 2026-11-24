"""One progress display for every long operation: stage, percent, bar and Cancel (M4-GUI-05)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from mcserver.application.progress import Progress
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.widgets import button

_SCALE = 1000
"""QProgressBar holds ints; fractions are shown in permille."""


class ProgressPanel(QWidget):
    """Hidden until ``start``; shows what the operation does now and lets the user cancel it."""

    cancel_requested = Signal()

    def __init__(self, messages: Messages, cancellable: bool = True) -> None:
        """Build the hidden panel; without ``cancellable`` there is no Cancel button."""
        super().__init__()
        self.setObjectName("progressPanel")
        self._messages = messages
        self.stage_label = QLabel()
        self.stage_label.setObjectName("progressStage")
        self.percent_label = QLabel()
        self.percent_label.setObjectName("progressPercent")
        self.cancel_button = button(messages.text("progress.cancel"), "secondary")
        self.cancel_button.clicked.connect(self._on_cancel)
        self.cancel_button.setVisible(cancellable)
        self._cancellable = cancellable
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(4)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.stage_label, 1)
        row.addWidget(self.percent_label)
        row.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(row)
        layout.addWidget(self.bar)
        self.hide()

    @property
    def running(self) -> bool:
        """Return whether an operation is shown."""
        return not self.isHidden()

    def start(self, text_key: str = "progress.working", cancellable: bool | None = None) -> None:
        """Show a busy indicator with ``text_key`` until the first report arrives."""
        if self.running:
            return
        self.stage_label.setText(self._messages.text(text_key))
        self.percent_label.clear()
        self.bar.setRange(0, 0)
        show_cancel = self._cancellable if cancellable is None else cancellable
        self.cancel_button.setVisible(show_cancel)
        self.cancel_button.setEnabled(True)
        self.show()

    def show_progress(self, progress: object) -> None:
        """Show one ``Progress`` report (other values are ignored)."""
        if not isinstance(progress, Progress) or not self.running:
            return
        if self.cancel_button.isEnabled():
            self.stage_label.setText(self._messages.text(f"progress.stage.{progress.stage.value}"))
        fraction = progress.fraction
        if fraction is None:
            self.bar.setRange(0, 0)
            self.percent_label.clear()
            return
        self.bar.setRange(0, _SCALE)
        self.bar.setValue(round(fraction * _SCALE))
        self.percent_label.setText(self._messages.text("progress.percent", percent=int(fraction * 100)))

    def show_cancelling(self) -> None:
        """Show that cancel was asked and the operation is cleaning up."""
        if not self.running:
            return
        self.cancel_button.setEnabled(False)
        self.stage_label.setText(self._messages.text("progress.cancelling"))

    def finish(self) -> None:
        """Hide the panel."""
        self.hide()
        self.bar.setRange(0, _SCALE)
        self.bar.setValue(0)

    def _on_cancel(self) -> None:
        self.show_cancelling()
        self.cancel_requested.emit()


__all__ = ["ProgressPanel"]
