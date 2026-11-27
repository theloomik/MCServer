"""Dialogs open modally inside the window: the window dims and a card sized to its content sits on top.

This follows the Windows ContentDialog pattern: one window, the server list stays in
place behind a dimming layer, and the dialog looks and behaves like a dialog (Escape
cancels, Enter confirms, the rest of the window cannot be used until it closes).
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QEvent, QEventLoop, QObject, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mcserver.presentation import theme

COMPACT_WIDTH = 460
"""Questions and confirmations."""
NORMAL_WIDTH = 580
"""Forms (create, edit, import, download)."""
MARGIN = 32
"""Space kept free around a dialog; taller content scrolls inside the card."""
_FIELDS = (QLineEdit, QAbstractSpinBox, QComboBox, QCheckBox, QListWidget, QPlainTextEdit)


class _Card(QFrame):
    """Holds one dialog: a scroll area (for very tall content) inside a card with a soft shadow."""

    def __init__(self, dialog: QDialog, width: int, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("modalCard")
        self.dialog = dialog
        self.preferred_width = width
        self.scroller = QScrollArea()
        self.scroller.setObjectName("modalScroll")
        self.scroller.setWidgetResizable(True)
        self.scroller.setFrameShape(QFrame.Shape.NoFrame)
        self.scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        dialog.setParent(self.scroller, Qt.WindowType.Widget)
        dialog.setMinimumWidth(0)
        dialog.setMaximumWidth(16777215)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        dialog.setSizePolicy(policy)
        self.scroller.setWidget(dialog)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.scroller, 1)
        # The buttons stay at the bottom of the card while long content scrolls above them.
        self.footer = take_footer(dialog)
        if self.footer is not None:
            layout.addWidget(self.footer)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 110 if theme.current == "dark" else 60))
        self.setGraphicsEffect(shadow)

    def fit(self, area: QRect) -> None:
        """Size the card to its dialog (width fixed by kind, height by content) and centre it in ``area``."""
        width = max(320, min(self.preferred_width, area.width() - 2 * MARGIN))
        layout = self.dialog.layout()
        if layout is not None:
            layout.activate()
        wanted = self.dialog.heightForWidth(width) if self.dialog.hasHeightForWidth() else -1
        if wanted <= 0:
            wanted = self.dialog.sizeHint().height()
        if self.footer is not None:
            wanted += self.footer.sizeHint().height()
        height = max(120, min(wanted + 12, area.height() - 2 * MARGIN))
        self.setGeometry(
            area.x() + (area.width() - width) // 2, area.y() + (area.height() - height) // 2, width, height
        )


class ModalHost(QWidget):
    """Show dialogs modally over ``parent``; widgets in ``blocked`` cannot be used meanwhile."""

    active_changed = Signal(bool)
    """``True`` when the first dialog opens, ``False`` when the last one closes."""

    def __init__(self, parent: QWidget, blocked: Sequence[QWidget] = ()) -> None:
        """Cover ``parent`` (resized with it) and disable ``blocked`` while a dialog is open."""
        super().__init__(parent)
        self.setObjectName("modalHost")
        self._blocked = tuple(blocked)
        self._cards: list[_Card] = []
        self._return_focus: dict[int, QWidget | None] = {}
        parent.installEventFilter(self)
        self.hide()

    # --- the same interface as PageHost ---------------------------------------------------------

    @property
    def pages(self) -> tuple[QDialog, ...]:
        """Return the open dialogs, bottom first."""
        return tuple(card.dialog for card in self._cards)

    @property
    def current_page(self) -> QDialog | None:
        """Return the dialog on top, if any."""
        return self._cards[-1].dialog if self._cards else None

    def open_page(self, dialog: QDialog, *, compact: bool = False) -> None:
        """Show ``dialog`` on top; it is removed when it finishes."""
        previous = QApplication.focusWidget()
        self._return_focus[id(dialog)] = previous
        if previous is not None:
            previous.destroyed.connect(lambda _object=None, key=id(dialog): self._return_focus.pop(key, None))
        if self._cards:
            self._cards[-1].hide()  # one dialog at a time; the one below comes back afterwards
        card = _Card(dialog, COMPACT_WIDTH if compact else NORMAL_WIDTH, self)
        self._cards.append(card)
        dialog.finished.connect(lambda _result, page=dialog: self._close(page))
        dialog.installEventFilter(self)
        first = len(self._cards) == 1
        if first:
            for widget in self._blocked:
                widget.setEnabled(False)
            self._cover()
            self.show()
        self.raise_()
        dialog.show()
        card.show()
        card.fit(self.rect())
        _focus_first_field(dialog)
        if first:
            self.active_changed.emit(True)

    def run_page(self, dialog: QDialog, *, compact: bool = True) -> int:
        """Show ``dialog`` and wait for its answer; return its result code."""
        loop = QEventLoop()
        dialog.finished.connect(loop.quit)
        self.open_page(dialog, compact=compact)
        if dialog.isVisible():
            loop.exec()
        return dialog.result()

    def dismiss_all(self) -> bool:
        """Cancel every dialog, top first; return ``False`` if one refuses (it is still working)."""
        for dialog in reversed(self.pages):
            dialog.reject()
            if dialog in self.pages:
                return False
        return True

    # --- behaviour ------------------------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        """Follow the window's size; refit a dialog whose content changed size."""
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize and self._cards:
            self._cover()
            self._cards[-1].fit(self.rect())
        elif event.type() == QEvent.Type.LayoutRequest and self._cards and watched is self._cards[-1].dialog:
            self._cards[-1].fit(self.rect())
        return super().eventFilter(watched, event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt override)
        """Dim the window behind the dialog."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150 if theme.current == "dark" else 96))
        painter.end()

    def mousePressEvent(self, event: object) -> None:  # noqa: N802 (Qt override)
        """Clicks on the dimmed area do nothing (the dialog stays; Escape or a button closes it)."""

    def _cover(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())

    def _close(self, dialog: QDialog) -> None:
        for index, card in enumerate(self._cards):
            if card.dialog is dialog:
                del self._cards[index]
                dialog.removeEventFilter(self)
                dialog.hide()
                # Hand the dialog back to its owner, who may still read its answer and deletes it.
                dialog.setParent(self.window(), Qt.WindowType.Widget)
                dialog.hide()
                if card.footer is not None:
                    card.footer.setParent(dialog)  # deleted with its dialog, as before
                    card.footer.hide()
                card.hide()
                card.deleteLater()
                break
        previous = self._return_focus.pop(id(dialog), None)
        if self._cards:
            top = self._cards[-1]
            top.show()
            top.fit(self.rect())
            _focus_first_field(top.dialog)
            return
        self.hide()
        for widget in self._blocked:
            widget.setEnabled(True)
        self.active_changed.emit(False)
        if previous is not None and previous.isVisible() and previous.isEnabled() and self.window().isVisible():
            previous.setFocus(Qt.FocusReason.OtherFocusReason)


def take_footer(dialog: QDialog) -> QFrame | None:
    """Move a ``FormDialog``'s button bar out of its scrolling content; return it (``None`` if it has none)."""
    footer = getattr(dialog, "footer", None)
    if not isinstance(footer, QFrame) or footer.isHidden():
        return None
    parent = footer.parentWidget()
    layout = parent.layout() if parent is not None else None
    if layout is not None:
        layout.removeWidget(footer)
    footer.setParent(None)
    return footer


def _focus_first_field(dialog: QDialog) -> None:
    """Focus the first field a keyboard user would fill in, else the default button, else the dialog."""
    candidates = [
        widget
        for widget in dialog.findChildren(QWidget)
        if widget.isVisibleTo(dialog) and widget.isEnabled() and widget.focusPolicy() & Qt.FocusPolicy.TabFocus
    ]
    chain: list[QWidget] = []
    current = dialog.nextInFocusChain()
    wanted = {id(widget) for widget in candidates}
    for _ in range(2000):
        if current is None or current is dialog:
            break
        if id(current) in wanted and current not in chain:
            chain.append(current)
        current = current.nextInFocusChain()
    for widget in chain:
        if isinstance(widget, _FIELDS) and not (isinstance(widget, QLineEdit) and widget.isReadOnly()):
            widget.setFocus(Qt.FocusReason.TabFocusReason)
            return
    for widget in candidates:
        if isinstance(widget, QPushButton) and widget.isDefault():
            widget.setFocus(Qt.FocusReason.TabFocusReason)
            return
    dialog.setFocus()


__all__ = ["COMPACT_WIDTH", "NORMAL_WIDTH", "ModalHost"]
