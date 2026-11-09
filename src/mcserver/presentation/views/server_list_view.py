"""Sidebar: brand, server list with status dots, empty and error states."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from mcserver.presentation import theme
from mcserver.presentation.controllers.server_list import ServerListState, ServerRow
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.status_text import STATUS_KEYS

_SERVER_ID_ROLE = Qt.ItemDataRole.UserRole
_SUBTITLE_ROLE = Qt.ItemDataRole.UserRole + 1
_STATUS_ROLE = Qt.ItemDataRole.UserRole + 2
_ITEM_HEIGHT = 58


class _ServerItemDelegate(QStyledItemDelegate):
    """Paint a server row: status dot, bold name, muted subtitle, accent bar when selected."""

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(option.rect.width(), _ITEM_HEIGHT)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(6, 3, -6, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.CARD_RAISED if selected else theme.CARD))
            painter.drawRoundedRect(rect, 8, 8)
        if selected:
            painter.setBrush(QColor(theme.ACCENT))
            painter.drawRoundedRect(QRect(rect.left(), rect.top() + 12, 3, rect.height() - 24), 1.5, 1.5)

        status = str(index.data(_STATUS_ROLE) or "unknown")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.STATUS_COLORS.get(status, theme.TEXT_FAINT)))
        painter.drawEllipse(QRect(rect.left() + 16, rect.center().y() - 4, 8, 8))

        text_left = rect.left() + 36
        text_width = rect.width() - 44
        name_font = QFont(option.font)
        name_font.setPointSizeF(option.font.pointSizeF() * 1.08)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(QColor(theme.ACCENT if selected else theme.TEXT))
        name_rect = QRect(text_left, rect.top() + 9, text_width, rect.height() // 2 - 6)
        name = painter.fontMetrics().elidedText(
            str(index.data(_SERVER_ID_ROLE)), Qt.TextElideMode.ElideRight, text_width
        )
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        sub_font = QFont(option.font)
        sub_font.setPointSizeF(option.font.pointSizeF() * 0.9)
        painter.setFont(sub_font)
        painter.setPen(QColor(theme.TEXT_MUTED))
        sub_rect = QRect(text_left, rect.center().y() + 1, text_width, rect.height() // 2 - 8)
        subtitle = painter.fontMetrics().elidedText(
            str(index.data(_SUBTITLE_ROLE) or ""), Qt.TextElideMode.ElideRight, text_width
        )
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, subtitle)
        painter.restore()


class ServerListView(QWidget):
    """Render ``ServerListState.servers`` and report which server the user picked."""

    server_selected = Signal(object)  # str | None
    refresh_requested = Signal()

    def __init__(self, messages: Messages, parent: QWidget | None = None) -> None:
        """Build the sidebar; content arrives through ``show_state``."""
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._messages = messages

        brand_mark = QLabel()
        brand_mark.setObjectName("brandMark")
        brand_mark.setFixedSize(22, 22)
        brand_title = QLabel(messages.text("app.title"))
        brand_title.setObjectName("brandTitle")
        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(brand_mark)
        brand.addWidget(brand_title, 1)

        caption = QLabel(messages.text("server_list.title").upper())
        caption.setObjectName("sectionCaption")
        self.refresh_button = QPushButton(messages.text("server_list.refresh"))
        self.refresh_button.setObjectName("refreshServers")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh_requested)
        header = QHBoxLayout()
        header.addWidget(caption, 1)
        header.addWidget(self.refresh_button)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("serverList")
        self.list_widget.setItemDelegate(_ServerItemDelegate(self.list_widget))
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list_widget.currentItemChanged.connect(self._on_current_item_changed)

        self.empty_label = QLabel(messages.text("server_list.empty"))
        self.empty_label.setObjectName("serverListEmpty")
        self.error_label = QLabel()
        self.error_label.setObjectName("serverListError")
        for label in (self.empty_label, self.error_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.list_widget)
        self.pages.addWidget(self.empty_label)
        self.pages.addWidget(self.error_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 20, 14, 14)
        layout.setSpacing(14)
        layout.addLayout(brand)
        layout.addSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.pages, 1)

    def show_state(self, state: ServerListState) -> None:
        """Replace the list content and selection with ``state``."""
        selected_id = state.selected.server_id if state.selected else None
        self.list_widget.blockSignals(True)
        try:
            self.list_widget.clear()
            for row in state.servers:
                item = QListWidgetItem(self._item_text(row))
                item.setData(_SERVER_ID_ROLE, row.server_id)
                item.setData(_SUBTITLE_ROLE, self._subtitle(row))
                item.setData(_STATUS_ROLE, row.status.value)
                item.setToolTip(row.server_id)
                self.list_widget.addItem(item)
                if row.server_id == selected_id:
                    self.list_widget.setCurrentItem(item)
            if selected_id is None:
                self.list_widget.setCurrentRow(-1)
        finally:
            self.list_widget.blockSignals(False)

        if state.list_error_key is not None:
            self.error_label.setText(self._messages.text(state.list_error_key))
            self.pages.setCurrentWidget(self.error_label)
        elif not state.servers:
            self.pages.setCurrentWidget(self.empty_label)
        else:
            self.pages.setCurrentWidget(self.list_widget)

    def server_ids(self) -> list[str]:
        """Return the identifiers in display order."""
        return [self.list_widget.item(index).data(_SERVER_ID_ROLE) for index in range(self.list_widget.count())]

    def _item_text(self, row: ServerRow) -> str:
        status = self._messages.text(STATUS_KEYS[row.status])
        return self._messages.text("server_list.item", server_id=row.server_id, status=status)

    def _subtitle(self, row: ServerRow) -> str:
        status = self._messages.text(STATUS_KEYS[row.status])
        memory = self._messages.text("server_details.memory_value", memory_mb=row.configuration.memory_mb)
        return self._messages.text("server_list.subtitle", status=status, memory=memory)

    def _on_current_item_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        self.server_selected.emit(current.data(_SERVER_ID_ROLE) if current is not None else None)
