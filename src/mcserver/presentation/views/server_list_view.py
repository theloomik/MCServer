"""Left panel: list of configured servers with empty and error states."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mcserver.presentation.controllers.server_list import ServerListState
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.status_text import STATUS_KEYS

_SERVER_ID_ROLE = Qt.ItemDataRole.UserRole


class ServerListView(QWidget):
    """Render ``ServerListState.servers`` and report which server the user picked."""

    server_selected = Signal(object)  # str | None
    refresh_requested = Signal()

    def __init__(self, messages: Messages, parent: QWidget | None = None) -> None:
        """Build the list panel; content arrives through ``show_state``."""
        super().__init__(parent)
        self._messages = messages

        title = QLabel(messages.text("server_list.title"))
        title.setObjectName("serverListTitle")
        self.refresh_button = QPushButton(messages.text("server_list.refresh"))
        self.refresh_button.setObjectName("refreshServers")
        self.refresh_button.clicked.connect(self.refresh_requested)
        header = QHBoxLayout()
        header.addWidget(title, 1)
        header.addWidget(self.refresh_button)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("serverList")
        self.list_widget.setUniformItemSizes(True)
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
        layout.addLayout(header)
        layout.addWidget(self.pages, 1)

    def show_state(self, state: ServerListState) -> None:
        """Replace the list content and selection with ``state``."""
        selected_id = state.selected.server_id if state.selected else None
        self.list_widget.blockSignals(True)
        try:
            self.list_widget.clear()
            for row in state.servers:
                status = self._messages.text(STATUS_KEYS[row.status])
                item = QListWidgetItem(self._messages.text("server_list.item", server_id=row.server_id, status=status))
                item.setData(_SERVER_ID_ROLE, row.server_id)
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

    def _on_current_item_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        self.server_selected.emit(current.data(_SERVER_ID_ROLE) if current is not None else None)
