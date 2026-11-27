"""Sidebar: brand, server list with status dots, empty and error states, and app actions (M4 design)."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from mcserver.presentation import icons, theme
from mcserver.presentation.controllers.server_list import ServerListState, ServerRow
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.memory_slider import format_gb
from mcserver.presentation.views.status_text import STATUS_KEYS
from mcserver.presentation.views.widgets import button, icon_button

_SERVER_ID_ROLE = Qt.ItemDataRole.UserRole
_SUBTITLE_ROLE = Qt.ItemDataRole.UserRole + 1
_STATUS_ROLE = Qt.ItemDataRole.UserRole + 2
_NAME_ROLE = Qt.ItemDataRole.UserRole + 3
_ITEM_HEIGHT = 50
SIDEBAR_WIDTH = 248


class _ServerItemDelegate(QStyledItemDelegate):
    """Paint a server row: status dot, name, muted subtitle; raised surface when selected."""

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(option.rect.width(), _ITEM_HEIGHT)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(0, 1, 0, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.setPen(QPen(QColor(theme.BORDER_STRONG), 1))
            painter.setBrush(QColor(theme.SURFACE_RAISED))
            painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.SURFACE_CARD))
            painter.drawRoundedRect(rect, 6, 6)

        status = str(index.data(_STATUS_ROLE) or "unknown")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.STATUS_COLORS.get(status, theme.TEXT_FAINT)))
        painter.drawEllipse(QRect(rect.left() + 12, rect.center().y() - 4, 8, 8))

        text_left = rect.left() + 30
        text_width = rect.width() - 40
        name_font = QFont(option.font)
        name_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(name_font)
        painter.setPen(QColor(theme.TEXT))
        name_rect = QRect(text_left, rect.top() + 7, text_width, 18)
        name = painter.fontMetrics().elidedText(
            str(index.data(_NAME_ROLE) or index.data(_SERVER_ID_ROLE)), Qt.TextElideMode.ElideRight, text_width
        )
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        sub_font = QFont(option.font)
        sub_font.setPixelSize(12)
        painter.setFont(sub_font)
        painter.setPen(QColor(theme.TEXT_MUTED))
        sub_rect = QRect(text_left, rect.top() + 26, text_width, 16)
        subtitle = painter.fontMetrics().elidedText(
            str(index.data(_SUBTITLE_ROLE) or ""), Qt.TextElideMode.ElideRight, text_width
        )
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, subtitle)
        painter.restore()


class ServerListView(QWidget):
    """Render ``ServerListState.servers`` and report which server the user picked."""

    server_selected = Signal(object)  # str | None
    refresh_requested = Signal()
    create_requested = Signal()
    import_requested = Signal()
    settings_requested = Signal()

    def __init__(self, messages: Messages, parent: QWidget | None = None) -> None:
        """Build the sidebar; content arrives through ``show_state``."""
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self._messages = messages

        brand_mark = QLabel()
        brand_mark.setObjectName("brandMark")
        brand_mark.setFixedSize(24, 24)
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_mark.setPixmap(icons.pixmap("server", theme.TEXT_ON_ACCENT, 14))
        brand_title = QLabel(messages.text("app.title"))
        brand_title.setObjectName("brandTitle")
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 0)
        brand.setSpacing(10)
        brand.addWidget(brand_mark)
        brand.addWidget(brand_title, 1)

        self.caption = QLabel(messages.text("server_list.title").upper())
        self.caption.setObjectName("sectionCaption")
        self.refresh_button = icon_button("restart", messages.text("server_list.refresh"), "refreshServers")
        self.refresh_button.clicked.connect(self.refresh_requested)
        self.add_button = icon_button("plus", messages.text("server_list.create"), "addServerButton")
        self.add_button.clicked.connect(self.create_requested)
        header = QHBoxLayout()
        header.setContentsMargins(8, 0, 0, 0)
        header.setSpacing(0)
        header.addWidget(self.caption, 1)
        header.addWidget(self.refresh_button)
        header.addWidget(self.add_button)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("serverList")
        self.list_widget.setAccessibleName(messages.text("a11y.server_list"))
        self.list_widget.setItemDelegate(_ServerItemDelegate(self.list_widget))
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setSpacing(1)
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list_widget.currentItemChanged.connect(self._on_current_item_changed)

        self.empty_label = QLabel(messages.text("server_list.empty"))
        self.empty_label.setObjectName("serverListEmpty")
        self.error_label = QLabel()
        self.error_label.setObjectName("serverListError")
        for label in (self.empty_label, self.error_label):
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            label.setWordWrap(True)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.list_widget)
        self.pages.addWidget(self.empty_label)
        self.pages.addWidget(self.error_label)

        self.create_button = button(messages.text("server_list.create"), "primary", "plus", "createServerButton")
        self.create_button.clicked.connect(self.create_requested)
        self.import_button = button(messages.text("server_list.import"), "ghost", "import")
        self.import_button.clicked.connect(self.import_requested)
        self.settings_button = button(messages.text("server_list.settings"), "ghost", "settings")
        self.settings_button.clicked.connect(self.settings_requested)
        footer = QFrame()
        footer.setObjectName("sidebarFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 10, 0, 0)
        footer_layout.setSpacing(4)
        footer_layout.addWidget(self.create_button)
        footer_layout.addWidget(self.import_button)
        footer_layout.addWidget(self.settings_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 14, 8, 12)
        layout.setSpacing(8)
        layout.addLayout(brand)
        layout.addSpacing(8)
        layout.addLayout(header)
        layout.addWidget(self.pages, 1)
        layout.addWidget(footer)

    def show_state(self, state: ServerListState) -> None:
        """Replace the list content and selection with ``state``."""
        selected_id = state.selected.server_id if state.selected else None
        self.caption.setText(self._messages.text("server_list.title_count", count=len(state.servers)).upper())
        self.list_widget.blockSignals(True)
        try:
            self.list_widget.clear()
            for row in state.servers:
                item = QListWidgetItem(self._item_text(row))
                item.setData(_SERVER_ID_ROLE, row.server_id)
                item.setData(_NAME_ROLE, row.configuration.name)
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
        return self._messages.text("server_list.item", server_id=row.configuration.name, status=status)

    def _subtitle(self, row: ServerRow) -> str:
        status = self._messages.text(STATUS_KEYS[row.status])
        memory = self._messages.text("memory.gb", value=format_gb(row.configuration.memory_mb))
        return self._messages.text("server_list.subtitle", status=status, memory=memory)

    def _on_current_item_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        self.server_selected.emit(current.data(_SERVER_ID_ROLE) if current is not None else None)
