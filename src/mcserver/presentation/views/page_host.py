"""Show dialogs as pages inside the main window's content area; the sidebar stays visible (M4 design).

A dialog keeps its own logic (``accept``/``reject``/``finished``); the host
only embeds it. Pages stack: a confirmation can open over Settings and
returns to it when answered.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QEventLoop, QObject, Qt
from PySide6.QtWidgets import QDialog, QFrame, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

PAGE_WIDTH = 640
COMPACT_WIDTH = 520


class PageHost(QStackedWidget):
    """A stack whose bottom widget is the dashboard; dialogs are pushed above it and popped when they finish."""

    def __init__(self, base: QWidget, parent: QWidget | None = None) -> None:
        """Show ``base`` until a page is opened."""
        super().__init__(parent)
        self.setObjectName("pageHost")
        self.base = base
        self.addWidget(base)
        self._pages: list[tuple[QDialog, QWidget]] = []

    @property
    def pages(self) -> tuple[QDialog, ...]:
        """Return the open pages, bottom first."""
        return tuple(dialog for dialog, _frame in self._pages)

    @property
    def current_page(self) -> QDialog | None:
        """Return the page on top, if any."""
        return self._pages[-1][0] if self._pages else None

    def open_page(self, dialog: QDialog, *, compact: bool = False) -> None:
        """Embed ``dialog`` above the current content and show it; it is removed when it finishes."""
        frame = QFrame()
        frame.setObjectName("pageFrame")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(24, 32 if not compact else 24, 24, 24)
        dialog.setParent(holder, Qt.WindowType.Widget)
        # A fixed width lets wrapped text compute its height; the page is never squeezed vertically (it scrolls).
        dialog.setMinimumWidth(0)
        dialog.setMaximumWidth(16777215)
        dialog.setFixedWidth(COMPACT_WIDTH if compact else PAGE_WIDTH)
        policy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)  # wrapped text gets the height it needs at this width
        dialog.setSizePolicy(policy)
        if compact:
            holder_layout.addStretch(1)
        holder_layout.addWidget(dialog, 0, Qt.AlignmentFlag.AlignHCenter)
        holder_layout.addStretch(1)
        scroll.setWidget(holder)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.addWidget(scroll)
        self._pages.append((dialog, frame))
        self.addWidget(frame)
        self.setCurrentWidget(frame)
        dialog.finished.connect(lambda _result, page=dialog: self._close_page(page))
        dialog.installEventFilter(self)
        dialog.show()
        _fit_height(dialog)
        dialog.setFocus()

    def run_page(self, dialog: QDialog, *, compact: bool = True) -> int:
        """Show ``dialog`` as a page and wait (in a local event loop) until it finishes; return its result code."""
        loop = QEventLoop()
        dialog.finished.connect(loop.quit)
        self.open_page(dialog, compact=compact)
        if dialog in self.pages:  # it may have finished during open_page
            loop.exec()
        return dialog.result()

    def dismiss_all(self) -> bool:
        """Cancel every open page from the top; return ``False`` if one refused (a running operation)."""
        while self._pages:
            dialog = self._pages[-1][0]
            dialog.reject()
            if self._pages and self._pages[-1][0] is dialog:
                return False
        return True

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        """Refit a page's height when its content changes (an error line appears, a field shows)."""
        if event.type() == QEvent.Type.LayoutRequest and isinstance(watched, QDialog) and watched in self.pages:
            _fit_height(watched)
        return super().eventFilter(watched, event)

    def _close_page(self, dialog: QDialog) -> None:
        for index, (page, frame) in enumerate(self._pages):
            if page is dialog:
                del self._pages[index]
                dialog.removeEventFilter(self)
                # Hand the dialog back to its owner (who may still read its answer and deletes it).
                dialog.hide()
                dialog.setParent(self.window(), Qt.WindowType.Widget)
                dialog.hide()
                self.removeWidget(frame)
                frame.deleteLater()
                break
        self.setCurrentWidget(self._pages[-1][1] if self._pages else self.base)


def _fit_height(dialog: QDialog) -> None:
    """Give ``dialog`` the height its content needs at its fixed width (wrapped text included)."""
    layout = dialog.layout()
    if layout is None:
        return
    layout.activate()
    height = (
        layout.totalHeightForWidth(dialog.width()) if layout.hasHeightForWidth() else layout.totalSizeHint().height()
    )
    if height > 0 and dialog.minimumHeight() != height:
        dialog.setMinimumHeight(height)


__all__ = ["PageHost"]
