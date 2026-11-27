"""Import an existing server folder: in place inside the servers folder, otherwise as a copy (M2-GUI-05)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

from mcserver.application.server_adoption import FolderContents
from mcserver.domain.server_configuration import is_safe_name
from mcserver.presentation.controllers.server_management import ManagementController
from mcserver.presentation.dialogs.form import FormDialog, primary_button, secondary_button
from mcserver.presentation.errors import UserMessage, render_message
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.memory_slider import MemorySlider
from mcserver.presentation.views.progress_panel import ProgressPanel

FolderPicker = Callable[[QWidget], str | None]
DEFAULT_MEMORY_MB = 4096


def pick_folder_with_system_dialog(messages: Messages) -> FolderPicker:
    """Return a picker that asks for a folder with the system dialog."""

    def pick(parent: QWidget) -> str | None:
        return QFileDialog.getExistingDirectory(parent, messages.text("adopt.folder.dialog_title")) or None

    return pick


class AdoptServerDialog(FormDialog):
    """Pick a folder, its JAR, an ID and memory; copying shows progress and can be cancelled."""

    def __init__(
        self,
        controller: ManagementController,
        messages: Messages,
        parent: QWidget | None = None,
        *,
        pick_folder: FolderPicker | None = None,
        system_memory_mb: int | None = None,
    ) -> None:
        """Build the empty form."""
        super().__init__(messages.text("adopt.title"), messages.text("adopt.subtitle"), parent)
        self._controller = controller
        self._messages = messages
        self._pick_folder = pick_folder or pick_folder_with_system_dialog(messages)
        self._contents: FolderContents | None = None
        self.imported_server_id: str | None = None

        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setPlaceholderText(messages.text("adopt.folder.placeholder"))
        self.browse_button = QPushButton(messages.text("adopt.folder.browse"))
        self.browse_button.setObjectName("secondaryButton")
        self.browse_button.clicked.connect(self.browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(self.browse_button)
        self.location_hint = self.add_field(messages.text("adopt.folder.label"), folder_row, " ")
        self.jar_combo = QComboBox()
        self.add_field(messages.text("adopt.jar.label"), self.jar_combo)
        self.id_edit = QLineEdit()
        self.id_edit.textChanged.connect(lambda _text: self._refresh())
        self.add_field(messages.text("adopt.server_id.label"), self.id_edit)
        self.memory_slider = MemorySlider(messages, system_memory_mb)
        self.add_field(messages.text("adopt.memory.label"), self.memory_slider)
        self.progress = ProgressPanel(messages, cancellable=False)  # the footer button cancels
        self.body.addWidget(self.progress)
        self.cancel_button = secondary_button(messages.text("adopt.cancel"))
        self.cancel_button.clicked.connect(self.reject)
        self.import_button = primary_button(messages.text("adopt.submit"))
        self.import_button.clicked.connect(self.submit)
        self.add_buttons(self.cancel_button, self.import_button)

        controller.copy_progress.connect(self._on_progress)
        controller.changed.connect(self._on_changed)
        controller.failed.connect(self._on_failed)
        controller.busy_changed.connect(lambda _busy: self._refresh())
        self._refresh()

    def browse(self) -> None:
        """Choose a folder and show what it contains."""
        folder = self._pick_folder(self)
        if folder:
            self.load_folder(folder)

    def load_folder(self, folder: str) -> None:
        """Inspect ``folder`` and fill the form from it."""
        result = self._controller.inspect_folder(folder)
        if isinstance(result, UserMessage):
            self._contents = None
            self.show_error(render_message(self._messages, result))
            self._refresh()
            return
        self.show_error(None)
        self._contents = result
        self.folder_edit.setText(result.folder)
        self.jar_combo.clear()
        self.jar_combo.addItems(result.jar_files)
        if not self.id_edit.text():
            self.id_edit.setText(result.directory if is_safe_name(result.directory) else "")
        if self.location_hint is not None:
            if not result.jar_files:
                self.location_hint.setText(self._messages.text("adopt.no_jars"))
            else:
                self.location_hint.setText(
                    self._messages.text("adopt.inside" if result.inside_root else "adopt.outside")
                )
        self._refresh()

    def submit(self) -> None:
        """Start the import."""
        contents = self._contents
        if contents is None or not self._can_submit():
            return
        self.show_error(None)
        self._controller.adopt(
            contents.folder,
            server_id=self.id_edit.text().strip(),
            jar_file=self.jar_combo.currentText(),
            memory_mb=self.memory_slider.value_mb(),
        )

    def _can_submit(self) -> bool:
        contents = self._contents
        return (
            contents is not None
            and bool(contents.jar_files)
            and is_safe_name(self.id_edit.text().strip())
            and not self._controller.busy
        )

    def _refresh(self) -> None:
        busy = self._controller.busy
        self.import_button.setEnabled(self._can_submit())
        self.import_button.setText(self._messages.text("adopt.submitting" if busy else "adopt.submit"))
        for widget in (self.browse_button, self.jar_combo, self.id_edit, self.memory_slider):
            widget.setEnabled(not busy)
        self.cancel_button.setText(self._messages.text("progress.cancel" if busy else "adopt.cancel"))
        self.cancel_button.setEnabled(True)
        if busy:
            self.progress.start("progress.stage.copying")
        else:
            self.progress.finish()

    def _on_progress(self, progress: object) -> None:
        self.progress.show_progress(progress)

    def _on_changed(self, server_id: object) -> None:
        if isinstance(server_id, str) and self.isVisible() and self._contents is not None:
            self.imported_server_id = server_id
            self.accept()

    def _on_failed(self, message: UserMessage) -> None:
        if self.isVisible():
            self.show_error(render_message(self._messages, message))

    def reject(self) -> None:
        """While a copy runs, cancel it (the partial copy is removed) instead of closing."""
        if self._controller.busy:
            self._controller.cancel_adopt()
            self.progress.show_cancelling()
            self.cancel_button.setEnabled(False)
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Keep the dialog open while copying."""
        if self._controller.busy:
            event.ignore()
            return
        super().closeEvent(event)
