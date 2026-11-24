"""Checks every view can pass: controls have names a screen reader can read (M4-GUI-07)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QComboBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTabBar,
    QTableView,
    QToolButton,
    QWidget,
)

_INPUTS = (QLineEdit, QAbstractSpinBox, QComboBox, QPlainTextEdit, QAbstractItemView)


def _labelled_inputs(root: QWidget) -> set[int]:
    return {id(label.buddy()) for label in root.findChildren(QLabel) if label.buddy() is not None}


def _describe(widget: QWidget) -> str:
    path = []
    current: QWidget | None = widget
    while current is not None and len(path) < 6:
        path.append(
            f"{type(current).__name__}#{current.objectName()}" if current.objectName() else type(current).__name__
        )
        current = current.parentWidget()
    return " < ".join(path)


def _internal(widget: QWidget, root: QWidget) -> bool:
    """Parts Qt builds itself: headers, popups, tab-bar scroll arrows, viewport helpers."""
    if widget.window() is not root.window() or isinstance(widget, QHeaderView):
        return True
    parent = widget.parentWidget()
    return isinstance(widget, QToolButton) and isinstance(parent, (QTabBar, QAbstractScrollArea, QTableView, QLineEdit))


def unnamed_controls(root: QWidget) -> list[str]:
    """Return controls that a screen reader would announce without a name."""
    problems: list[str] = []
    buddies = _labelled_inputs(root)
    for widget in root.findChildren(QWidget):
        if not widget.isVisibleTo(root) or _internal(widget, root):
            continue
        if isinstance(widget, QAbstractButton):
            if not (widget.text().replace("&", "").strip() or widget.accessibleName()):
                problems.append(_describe(widget))
        elif isinstance(widget, _INPUTS):
            if isinstance(widget, QLineEdit) and isinstance(widget.parent(), (QComboBox, QAbstractSpinBox)):
                continue  # the editor inside a combo box or spin box shares its owner's name
            if widget.parent() is not None and isinstance(widget.parent().parent(), QAbstractItemView):
                continue  # item editors
            if not widget.accessibleName() and id(widget) not in buddies:
                problems.append(_describe(widget))
    return problems


def unreachable_controls(root: QWidget) -> list[str]:
    """Return visible enabled controls the keyboard cannot reach (no Tab focus)."""
    problems: list[str] = []
    for widget in root.findChildren(QWidget):
        if not widget.isVisibleTo(root) or not widget.isEnabled() or _internal(widget, root):
            continue
        if isinstance(widget, QTabBar):
            continue
        if isinstance(widget, (QAbstractButton, *_INPUTS)):
            if isinstance(widget, QLineEdit) and isinstance(widget.parent(), (QComboBox, QAbstractSpinBox)):
                continue
            if not widget.focusPolicy() & Qt.FocusPolicy.TabFocus:
                problems.append(_describe(widget))
    return problems


__all__ = ["unnamed_controls", "unreachable_controls"]
