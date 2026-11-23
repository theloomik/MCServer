"""Edit a server: name, memory, JAR, extra Java arguments and Java for this server (M2-GUI-03)."""

from __future__ import annotations

import shlex
from collections.abc import Callable

from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QWidget

from mcserver.domain.server_configuration import MAX_MEMORY_MB, MIN_MEMORY_MB, ServerConfiguration
from mcserver.presentation.controllers.server_management import ManagementController
from mcserver.presentation.dialogs.form import FormDialog, primary_button, secondary_button
from mcserver.presentation.errors import render_message
from mcserver.presentation.i18n import Messages

JavaPicker = Callable[[QWidget], str | None]
MEMORY_STEP_MB = 512


def split_arguments(text: str) -> tuple[str, ...]:
    """Split the arguments line on spaces; quotes keep spaces inside one argument."""
    return tuple(token.strip('"') for token in shlex.split(text, posix=False) if token.strip('"'))


def join_arguments(arguments: tuple[str, ...]) -> str:
    """Show arguments on one line, quoting those that contain spaces."""
    return " ".join(f'"{argument}"' if " " in argument else argument for argument in arguments)


def pick_java_with_system_dialog(messages: Messages) -> JavaPicker:
    """Return a picker that asks for ``java.exe`` with the system file dialog."""

    def pick(parent: QWidget) -> str | None:
        path, _filter = QFileDialog.getOpenFileName(
            parent, messages.text("java.choose.dialog_title"), "", messages.text("java.choose.filter")
        )
        return path or None

    return pick


class EditServerDialog(FormDialog):
    """Edit one server; validation errors from the domain are shown above the buttons."""

    def __init__(
        self,
        controller: ManagementController,
        configuration: ServerConfiguration,
        messages: Messages,
        parent: QWidget | None = None,
        *,
        running: bool = False,
        pick_java: JavaPicker | None = None,
    ) -> None:
        """Build the form from ``configuration``; ``running`` locks the JAR choice."""
        super().__init__(messages.text("edit.title", server_id=configuration.server_id), parent=parent)
        self._controller = controller
        self._configuration = configuration
        self._messages = messages
        self._pick_java = pick_java or pick_java_with_system_dialog(messages)

        self.name_edit = QLineEdit(configuration.display_name)
        self.name_edit.setPlaceholderText(configuration.server_id)
        self.add_field(
            messages.text("edit.display_name.label"),
            self.name_edit,
            messages.text("edit.display_name.hint", server_id=configuration.server_id),
        )
        self.memory_spin = QSpinBox()
        self.memory_spin.setRange(MIN_MEMORY_MB, MAX_MEMORY_MB)
        self.memory_spin.setSingleStep(MEMORY_STEP_MB)
        self.memory_spin.setSuffix(messages.text("create.memory.suffix"))
        self.memory_spin.setValue(configuration.memory_mb)
        self.add_field(messages.text("edit.memory.label"), self.memory_spin)
        self.jar_combo = QComboBox()
        self.jar_combo.addItems(controller.jar_files(configuration))
        self.jar_combo.setCurrentText(configuration.jar_file)
        self.jar_combo.setEnabled(not running)
        self.add_field(
            messages.text("edit.jar.label"), self.jar_combo, messages.text("edit.jar.hint_running") if running else ""
        )
        self.jvm_edit = QLineEdit(join_arguments(configuration.jvm_arguments))
        self.add_field(messages.text("edit.jvm.label"), self.jvm_edit, messages.text("edit.jvm.hint"))
        self.java_edit = QLineEdit(configuration.java_path or "")
        self.java_edit.setPlaceholderText(messages.text("edit.java.auto"))
        self.java_edit.setReadOnly(True)
        self.java_choose = QPushButton(messages.text("edit.java.choose"))
        self.java_choose.setObjectName("secondaryButton")
        self.java_choose.clicked.connect(self._choose_java)
        self.java_clear = QPushButton(messages.text("edit.java.clear"))
        self.java_clear.setObjectName("secondaryButton")
        self.java_clear.clicked.connect(self.java_edit.clear)
        java_row = QHBoxLayout()
        java_row.addWidget(self.java_edit, 1)
        java_row.addWidget(self.java_choose)
        java_row.addWidget(self.java_clear)
        self.add_field(messages.text("edit.java.label"), java_row)
        self.add_note(messages.text("edit.note"))
        self.cancel_button = secondary_button(messages.text("edit.cancel"))
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = primary_button(messages.text("edit.save"))
        self.save_button.clicked.connect(self.save)
        self.add_buttons(self.cancel_button, self.save_button)

    def save(self) -> None:
        """Validate and store; close on success, otherwise show why not."""
        try:
            arguments = split_arguments(self.jvm_edit.text())
        except ValueError:
            self.show_error(self._messages.text("errors.invalid_configuration", reason=self.jvm_edit.text()))
            return
        error = self._controller.save_edit(
            self._configuration.server_id,
            display_name=self.name_edit.text().strip(),
            memory_mb=self.memory_spin.value(),
            jar_file=self.jar_combo.currentText(),
            jvm_arguments=arguments,
            java_path=self.java_edit.text().strip() or None,
        )
        if error is not None:
            self.show_error(render_message(self._messages, error))
            return
        self.accept()

    def _choose_java(self) -> None:
        path = self._pick_java(self)
        if path:
            self.java_edit.setText(path)
