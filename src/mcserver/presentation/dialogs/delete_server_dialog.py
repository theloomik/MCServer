"""Confirm deleting a server, optionally moving its folder to the Recycle Bin (M2-GUI-04)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QWidget

from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.presentation.dialogs.form import FormDialog, primary_button, secondary_button
from mcserver.presentation.i18n import Messages


class DeleteServerDialog(FormDialog):
    """Name the server, offer "also move the folder to the Recycle Bin" (off by default)."""

    def __init__(
        self, configuration: ServerConfiguration, folder: Path, messages: Messages, parent: QWidget | None = None
    ) -> None:
        """Build the confirmation for ``configuration`` whose files are in ``folder``."""
        super().__init__(
            messages.text("delete.title", name=configuration.name),
            messages.text("delete.text", name=configuration.name),
            parent,
        )
        self.files_check = QCheckBox(messages.text("delete.files"))
        self.body.addWidget(self.files_check)
        self.files_hint = self.add_note(messages.text("delete.files_hint", path=str(folder)))
        self.cancel_button = secondary_button(messages.text("delete.cancel"))
        self.cancel_button.clicked.connect(self.reject)
        self.delete_button = primary_button(messages.text("delete.confirm"))
        self.delete_button.clicked.connect(self.accept)
        # Cancel is the default action: deleting needs a deliberate click.
        self.add_buttons(self.delete_button, self.cancel_button)

    @property
    def remove_files(self) -> bool:
        """Return whether the folder should go to the Recycle Bin too."""
        return self.files_check.isChecked()
