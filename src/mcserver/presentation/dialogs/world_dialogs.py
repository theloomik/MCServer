"""Questions the Worlds tab asks: names, files and confirmations (M3-GUI-07)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PySide6.QtWidgets import QFileDialog, QWidget

from mcserver.presentation.dialogs.confirm_dialog import Choice, ask, run_dialog
from mcserver.presentation.dialogs.prompt_dialog import PromptDialog, PromptField
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
        """Ask for a name and an optional seed on one page."""
        text = self._messages.text
        dialog = PromptDialog(
            text("worlds.new.title"),
            [PromptField("name", text("worlds.new.name")), PromptField("seed", text("worlds.new.seed"), optional=True)],
            text("worlds.new.create"),
            text("dialog.cancel"),
            self._parent,
        )
        accepted = run_dialog(self._parent, dialog) == PromptDialog.DialogCode.Accepted
        values = dict(dialog.values)
        dialog.deleteLater()
        return (values["name"], values["seed"]) if accepted else None

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
        dialog = PromptDialog(
            text("worlds.import.title"),
            [PromptField("name", text("worlds.import.name"), suggested)],
            text("worlds.import.ok"),
            text("dialog.cancel"),
            self._parent,
        )
        accepted = run_dialog(self._parent, dialog) == PromptDialog.DialogCode.Accepted
        name = dialog.values.get("name", "")
        dialog.deleteLater()
        return name if accepted and name else None

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
        answer = ask(
            self._parent,
            text("worlds.delete.title", name=name),
            text("worlds.delete.text", name=name),
            [Choice("cancel", text("dialog.cancel")), Choice("yes", text("dialog.move_to_recycle_bin"), "danger")],
            tone="danger",
            default="cancel",
        )
        return answer == "yes"
