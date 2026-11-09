"""Right panel: configuration and status of the selected server."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from mcserver.presentation.controllers.server_list import ServerListState, ServerStatus
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.status_text import STATUS_KEYS

DETAIL_FIELDS = ("server_id", "directory", "location", "jar_file", "memory", "status")
"""Rows of the details form; each has the label key ``server_details.field.<name>``."""


class ServerDetailsView(QWidget):
    """Render ``ServerListState.selected``; shows a hint when nothing is selected.

    The location is computed from the servers folder and the configured
    directory name; nothing is read from disk.
    """

    def __init__(self, messages: Messages, servers_root: Path, parent: QWidget | None = None) -> None:
        """Build the panel for servers inside ``servers_root``."""
        super().__init__(parent)
        self._messages = messages
        self._servers_root = servers_root

        self.title_label = QLabel()
        self.title_label.setObjectName("serverTitle")
        font = self.title_label.font()
        font.setPointSizeF(font.pointSizeF() * 1.4)
        font.setBold(True)
        self.title_label.setFont(font)

        self.values: dict[str, QLabel] = {}
        form = QFormLayout()
        for field in DETAIL_FIELDS:
            value = QLabel()
            value.setObjectName(f"detail_{field}")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.values[field] = value
            form.addRow(QLabel(messages.text(f"server_details.field.{field}")), value)
        self.next_launch_note = QLabel(messages.text("server_details.next_launch_note"))
        self.next_launch_note.setObjectName("nextLaunchNote")
        self.next_launch_note.setWordWrap(True)

        details_page = QWidget()
        details_layout = QVBoxLayout(details_page)
        details_layout.addWidget(self.title_label)
        details_layout.addLayout(form)
        details_layout.addWidget(self.next_launch_note)
        details_layout.addStretch(1)

        self.empty_label = QLabel(messages.text("server_details.empty"))
        self.empty_label.setObjectName("serverDetailsEmpty")
        self.error_label = QLabel()
        self.error_label.setObjectName("serverDetailsError")
        for label in (self.empty_label, self.error_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)

        self.pages = QStackedWidget()
        self.details_page = details_page
        self.pages.addWidget(details_page)
        self.pages.addWidget(self.empty_label)
        self.pages.addWidget(self.error_label)
        layout = QVBoxLayout(self)
        layout.addWidget(self.pages)
        self.pages.setCurrentWidget(self.empty_label)

    def show_state(self, state: ServerListState) -> None:
        """Show the selected server, an error, or the empty-selection hint."""
        if state.details_error_key is not None:
            self.error_label.setText(self._messages.text(state.details_error_key))
            self.pages.setCurrentWidget(self.error_label)
            return
        row = state.selected
        if row is None:
            self.pages.setCurrentWidget(self.empty_label)
            return
        configuration = row.configuration
        self.title_label.setText(configuration.server_id)
        self.values["server_id"].setText(configuration.server_id)
        self.values["directory"].setText(configuration.directory)
        self.values["location"].setText(str(self._servers_root / configuration.directory))
        self.values["jar_file"].setText(configuration.jar_file)
        self.values["memory"].setText(
            self._messages.text("server_details.memory_value", memory_mb=configuration.memory_mb)
        )
        self.values["status"].setText(self._messages.text(STATUS_KEYS[row.status]))
        self.values["status"].setToolTip(
            self._messages.text("status.server.unknown_hint") if row.status is ServerStatus.UNKNOWN else ""
        )
        self.pages.setCurrentWidget(self.details_page)
