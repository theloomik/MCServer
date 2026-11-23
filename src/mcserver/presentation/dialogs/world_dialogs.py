"""Questions the Worlds tab asks: names, files and confirmations (M3-GUI-07)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PySide6.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QMessageBox, QWidget

from mcserver.presentation.i18n import Messages


class WorldDialogs(Protocol):
    """Ask the user about world operations; tests replace it with answers."""

    def new_world(self) -> tuple[str, str] | None:
        """Return the name and seed (may be empty) of a new world, or ``None``."""

    def import_source(self, zip_file: bool) -> str | None:
        """Return the folder or ZIP file to import, or ``None``."""

    def world_name(self, suggested: str) -> str | None:
        """Return the name for an imported world, or ``None``."""

    def export_path(self, name: str) -> str | None:
        """Return where to write the ZIP of world ``name``, or ``None``."""

    def confirm_delete(self, name: str) -> bool:
        """Return whether world ``name`` should go to the Recycle Bin."""


class QtWorldDialogs:
    """Standard Qt dialogs for ``WorldDialogs``."""

    def __init__(self, parent: QWidget, messages: Messages) -> None:
        """Show dialogs over ``parent``."""
        self._parent = parent
        self._messages = messages

    def new_world(self) -> tuple[str, str] | None:
        """Ask for a name, then an optional seed."""
        text = self._messages.text
        name, accepted = QInputDialog.getText(
            self._parent, text("worlds.new.title"), text("worlds.new.name"), QLineEdit.EchoMode.Normal
        )
        if not accepted or not name.strip():
            return None
        seed, accepted = QInputDialog.getText(
            self._parent, text("worlds.new.title"), text("worlds.new.seed"), QLineEdit.EchoMode.Normal
        )
        return (name.strip(), seed.strip()) if accepted else None

    def import_source(self, zip_file: bool) -> str | None:
        """Ask for a world folder or a ZIP file."""
        text = self._messages.text
        if zip_file:
            path, _filter = QFileDialog.getOpenFileName(
                self._parent, text("worlds.import_zip.title"), str(Path.home()), text("worlds.zip_filter")
            )
        else:
            path = QFileDialog.getExistingDirectory(self._parent, text("worlds.import_folder.title"), str(Path.home()))
        return path or None

    def world_name(self, suggested: str) -> str | None:
        """Ask for the imported world's name."""
        text = self._messages.text
        name, accepted = QInputDialog.getText(
            self._parent, text("worlds.import.title"), text("worlds.import.name"), QLineEdit.EchoMode.Normal, suggested
        )
        return name.strip() if accepted and name.strip() else None

    def export_path(self, name: str) -> str | None:
        """Ask where to save the archive."""
        text = self._messages.text
        path, _filter = QFileDialog.getSaveFileName(
            self._parent, text("worlds.export.title"), str(Path.home() / f"{name}.zip"), text("worlds.zip_filter")
        )
        return path or None

    def confirm_delete(self, name: str) -> bool:
        """Ask before moving a world to the Recycle Bin."""
        text = self._messages.text
        answer = QMessageBox.question(
            self._parent,
            text("worlds.delete.title", name=name),
            text("worlds.delete.text", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes
