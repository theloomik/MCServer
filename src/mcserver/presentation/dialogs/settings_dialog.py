"""Application settings: servers folder, Java, timeouts and the legacy import (M2-GUI-01)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QWidget

from mcserver.application.errors import InvalidJavaExecutable
from mcserver.application.java_setup import JavaSetup
from mcserver.application.settings import STARTUP_TIMEOUT_RANGE, STOP_TIMEOUT_RANGE, ApplicationSettings
from mcserver.presentation.controllers.server_management import ManagementController
from mcserver.presentation.dialogs.edit_server_dialog import JavaPicker, pick_java_with_system_dialog
from mcserver.presentation.dialogs.form import FormDialog, primary_button, secondary_button
from mcserver.presentation.errors import describe_error, render_message
from mcserver.presentation.i18n import Messages

FolderOpener = Callable[[Path], bool]


class SettingsDialog(FormDialog):
    """Show and change application settings; the Java choice is validated before it is saved."""

    import_legacy_requested = Signal()

    def __init__(
        self,
        controller: ManagementController,
        settings: ApplicationSettings,
        java: JavaSetup | None,
        messages: Messages,
        parent: QWidget | None = None,
        *,
        open_folder: FolderOpener | None = None,
        pick_java: JavaPicker | None = None,
    ) -> None:
        """Build the form from the current ``settings``."""
        super().__init__(messages.text("settings.title"), parent=parent)
        self._controller = controller
        self._java = java
        self._messages = messages
        self._open_folder = open_folder
        self._pick_java = pick_java or pick_java_with_system_dialog(messages)
        self._java_executable = settings.java_executable

        folder = QLineEdit(str(controller.servers_root))
        folder.setReadOnly(True)
        self.open_folder_button = QPushButton(messages.text("settings.open_folder"))
        self.open_folder_button.setObjectName("secondaryButton")
        self.open_folder_button.clicked.connect(self._open)
        folder_row = QHBoxLayout()
        folder_row.addWidget(folder, 1)
        folder_row.addWidget(self.open_folder_button)
        self.add_field(messages.text("settings.servers_folder"), folder_row)

        # A read-only field (not a wrapped label): it keeps the row height stable for long paths.
        self.java_label = QLineEdit()
        self.java_label.setReadOnly(True)
        self.java_choose = QPushButton(messages.text("settings.java.choose"))
        self.java_choose.setObjectName("secondaryButton")
        self.java_choose.clicked.connect(self.choose_java)
        self.java_auto = QPushButton(messages.text("settings.java.auto"))
        self.java_auto.setObjectName("secondaryButton")
        self.java_auto.clicked.connect(self.use_automatic_java)
        self.add_field(messages.text("settings.java.label"), self.java_label)
        java_buttons = QHBoxLayout()
        java_buttons.addWidget(self.java_choose)
        java_buttons.addWidget(self.java_auto)
        java_buttons.addStretch(1)
        self.body.addLayout(java_buttons)
        self.body.addSpacing(10)

        self.stop_spin = self._seconds(STOP_TIMEOUT_RANGE, settings.stop_timeout_seconds)
        self.add_field(
            messages.text("settings.stop_timeout.label"), self.stop_spin, messages.text("settings.stop_timeout.hint")
        )
        self.startup_spin = self._seconds(STARTUP_TIMEOUT_RANGE, settings.startup_timeout_seconds)
        self.add_field(
            messages.text("settings.startup_timeout.label"),
            self.startup_spin,
            messages.text("settings.startup_timeout.hint"),
        )
        self.auto_restart_check = QCheckBox(messages.text("settings.auto_restart.label"))
        self.auto_restart_check.setChecked(settings.auto_restart)
        self.body.addWidget(self.auto_restart_check)
        hint = QLabel(messages.text("settings.auto_restart.hint"))
        hint.setObjectName("fieldHint")
        hint.setWordWrap(True)
        self.body.addWidget(hint)
        self.body.addSpacing(6)
        self.import_button = secondary_button(messages.text("settings.import_legacy"))
        self.import_button.clicked.connect(self._request_import)
        self.body.addWidget(self.import_button)
        self.cancel_button = secondary_button(messages.text("settings.cancel"))
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = primary_button(messages.text("settings.save"))
        self.save_button.clicked.connect(self.save)
        self.add_buttons(self.cancel_button, self.save_button)
        self._show_java()

    def _seconds(self, limits: tuple[int, int], value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(*limits)
        spin.setSingleStep(10)
        spin.setSuffix(self._messages.text("settings.seconds"))
        spin.setValue(value)
        return spin

    def choose_java(self) -> None:
        """Pick ``java.exe``; it is checked now and saved with the other settings."""
        path = self._pick_java(self)
        if not path:
            return
        if self._java is not None:
            try:
                self._java.check(path)  # validated now, applied when the settings are saved
            except InvalidJavaExecutable as error:
                self.show_error(render_message(self._messages, describe_error(error)))
                return
        self.show_error(None)
        self._java_executable = path
        self._show_java()

    def use_automatic_java(self) -> None:
        """Go back to automatic Java detection."""
        self._java_executable = None
        self._show_java()

    def save(self) -> None:
        """Store the settings; close on success."""
        error = self._controller.update_settings(
            java_executable=self._java_executable,
            stop_timeout_seconds=self.stop_spin.value(),
            startup_timeout_seconds=self.startup_spin.value(),
            auto_restart=self.auto_restart_check.isChecked(),
        )
        if error is not None:
            self.show_error(render_message(self._messages, error))
            return
        self.accept()

    def _show_java(self) -> None:
        """Show the chosen executable, or "detect automatically"."""
        self.java_label.setText(self._java_executable or self._messages.text("settings.java.auto"))

    def _open(self) -> None:
        if self._open_folder is not None:
            self._open_folder(self._controller.servers_root)

    def _request_import(self) -> None:
        self.import_legacy_requested.emit()
