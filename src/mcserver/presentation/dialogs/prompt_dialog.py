"""Ask for one or more short texts inside the window (replaces ``QInputDialog``, M4 design)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtWidgets import QLineEdit, QWidget

from mcserver.presentation.dialogs.form import FormDialog, primary_button, secondary_button


@dataclass(frozen=True, slots=True)
class PromptField:
    """One text field: its ``key`` in the answer, ``label``, initial ``value`` and whether it may stay empty."""

    key: str
    label: str
    value: str = ""
    optional: bool = False


class PromptDialog(FormDialog):
    """Collect texts; ``values`` holds the trimmed answers after ``accept``."""

    def __init__(
        self,
        title: str,
        fields: Sequence[PromptField],
        ok_text: str,
        cancel_text: str,
        parent: QWidget | None = None,
    ) -> None:
        """Build one line edit per field; OK is enabled while every required field has text."""
        super().__init__(title, "", parent)
        self._fields = tuple(fields)
        self.edits: dict[str, QLineEdit] = {}
        self.values: dict[str, str] = {}
        for field in self._fields:
            edit = QLineEdit(field.value)
            edit.textChanged.connect(self._update)
            edit.returnPressed.connect(self._submit)
            self.edits[field.key] = edit
            self.add_field(field.label, edit)
        cancel = secondary_button(cancel_text)
        cancel.clicked.connect(self.reject)
        self.ok_button = primary_button(ok_text)
        self.ok_button.clicked.connect(self._submit)
        self.add_buttons(cancel, self.ok_button)
        self._update()
        if self._fields:
            first = self.edits[self._fields[0].key]
            first.setFocus()
            first.selectAll()

    def _ready(self) -> bool:
        return all(field.optional or self.edits[field.key].text().strip() for field in self._fields)

    def _update(self) -> None:
        self.ok_button.setEnabled(self._ready())

    def _submit(self) -> None:
        if not self._ready():
            return
        self.values = {key: edit.text().strip() for key, edit in self.edits.items()}
        self.accept()


__all__ = ["PromptDialog", "PromptField"]
