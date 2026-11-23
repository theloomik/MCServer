"""Choose Paper or Vanilla and a version, then download the verified server JAR (M3-GUI-06)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QWidget,
)

from mcserver.application.server_catalog import ServerType
from mcserver.presentation.controllers.jar_catalog import CatalogState, JarCatalogController
from mcserver.presentation.dialogs.form import FormDialog, primary_button, secondary_button
from mcserver.presentation.errors import render_message
from mcserver.presentation.i18n import Messages


class DownloadJarDialog(FormDialog):
    """Pick a version and download it; ``path`` holds the verified file after ``accept``."""

    def __init__(self, controller: JarCatalogController, messages: Messages, parent: QWidget | None = None) -> None:
        """Build the dialog and start loading versions."""
        super().__init__(messages.text("catalog.title"), messages.text("catalog.subtitle"), parent)
        self._controller = controller
        self._messages = messages
        self.path: str | None = None

        self.type_combo = QComboBox()
        for server_type in (ServerType.PAPER, ServerType.VANILLA):
            self.type_combo.addItem(messages.text(f"catalog.type.{server_type.value}"), server_type.value)
        self.type_combo.currentIndexChanged.connect(self._on_type)
        self.unstable_check = QCheckBox(messages.text("catalog.unstable"))
        self.unstable_check.toggled.connect(lambda checked: controller.load(include_unstable=checked))
        type_row = QHBoxLayout()
        type_row.addWidget(self.type_combo, 1)
        type_row.addWidget(self.unstable_check)
        self.add_field(messages.text("catalog.type.label"), type_row, messages.text("catalog.type.hint"))

        self.version_list = QListWidget()
        self.version_list.setObjectName("versionList")
        self.version_list.setMinimumHeight(200)
        self.version_list.currentItemChanged.connect(self._on_version)
        self.add_field(messages.text("catalog.version.label"), self.version_list)

        self.details = QLabel()
        self.details.setObjectName("fieldHint")
        self.details.setWordWrap(True)
        self.body.addWidget(self.details)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        self.body.addWidget(self.progress)

        self.cancel_button = secondary_button(messages.text("catalog.cancel"))
        self.cancel_button.clicked.connect(self.reject)
        self.download_button = primary_button(messages.text("catalog.download"))
        self.download_button.clicked.connect(controller.download)
        self.add_buttons(self.cancel_button, self.download_button)

        controller.state_changed.connect(self._show)
        controller.progress.connect(self._on_progress)
        controller.downloaded.connect(self._on_downloaded)
        self.finished.connect(self._disconnect)
        self._shown_versions: tuple[object, ...] = ()
        self._show(controller.state)
        controller.load(ServerType.PAPER, False)

    def _disconnect(self) -> None:
        # The controller outlives this dialog (it belongs to the main window).
        self._controller.state_changed.disconnect(self._show)
        self._controller.progress.disconnect(self._on_progress)
        self._controller.downloaded.disconnect(self._on_downloaded)

    def _on_type(self) -> None:
        value = self.type_combo.currentData()
        if value in {server_type.value for server_type in ServerType}:
            self._controller.load(ServerType(value))

    def _on_version(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        self._controller.select(current.data(Qt.ItemDataRole.UserRole) if current is not None else None)

    def _show(self, state: CatalogState) -> None:
        text = self._messages.text
        if state.versions != self._shown_versions:
            self._shown_versions = state.versions
            self.version_list.blockSignals(True)
            self.version_list.clear()
            for version in state.versions:
                label = version.version if version.stable else text("catalog.version.unstable", version=version.version)
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, version.version)
                self.version_list.addItem(item)
            if state.versions and state.selected is None:
                self.version_list.setCurrentRow(0)
            self.version_list.blockSignals(False)
            if state.versions and state.selected is None:
                self._controller.select(state.versions[0].version)  # the newest version, resolved right away
                return
        self.details.setText(self._details(state))
        downloading = state.downloading
        self.progress.setVisible(downloading or state.loading or state.resolving)
        if not downloading:
            self.progress.setRange(0, 0)
        for widget in (self.type_combo, self.unstable_check, self.version_list):
            widget.setEnabled(not downloading)
        self.download_button.setEnabled(state.can_download)
        self.download_button.setText(text("catalog.downloading" if downloading else "catalog.download"))
        self.cancel_button.setText(text("catalog.stop" if downloading else "catalog.cancel"))
        self.cancel_button.setEnabled(not state.cancelling)
        self.show_error(render_message(self._messages, state.error) if state.error is not None else None)

    def _details(self, state: CatalogState) -> str:
        text = self._messages.text
        if state.loading:
            return text("catalog.loading")
        if state.resolving:
            return text("catalog.resolving")
        download = state.download
        if download is None:
            return ""
        size = f"{download.size_bytes / (1024 * 1024):.0f}" if download.size_bytes else "?"
        java = text("catalog.java", java=download.java_major) if download.java_major else text("catalog.java_unknown")
        lines = [text("catalog.details", file_name=download.file_name, size=size), java]
        if not download.stable:
            lines.append(text("catalog.experimental_build"))
        if state.cancelling:
            lines.append(text("catalog.cancelling"))
        return "\n".join(lines)

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(min(1000, done * 1000 // total))

    def _on_downloaded(self, path: str) -> None:
        self.path = path
        self.accept()

    def reject(self) -> None:
        """Cancel the download first; the dialog closes once it stopped."""
        if self._controller.state.busy:
            self._controller.cancel()
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stay open while a download runs (it is cancelled instead)."""
        if self._controller.state.busy:
            self._controller.cancel()
            event.ignore()
            return
        super().closeEvent(event)
