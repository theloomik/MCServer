"""Create a server: a name, the server software, how much memory, the EULA (UX overhaul).

Beginners see four things and one primary button. The folder name, which follows the
server name, waits under "Advanced" for those who want a different one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePath

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QVBoxLayout, QWidget

from mcserver.domain.server_configuration import MAX_MEMORY_MB, MIN_MEMORY_MB, ServerConfiguration
from mcserver.presentation import icons, theme
from mcserver.presentation.controllers.server_creation import CreationForm, CreationState, ServerCreationController
from mcserver.presentation.dialogs.form import FormDialog, primary_button, secondary_button
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.memory_slider import MemorySlider
from mcserver.presentation.views.widgets import WrapRow, button, repolish

JarPicker = Callable[[QWidget], str | None]


def pick_jar_with_system_dialog(messages: Messages) -> JarPicker:
    """Return a picker that opens the native "open file" dialog for ``.jar`` files."""

    def pick(parent: QWidget) -> str | None:
        path, _filter = QFileDialog.getOpenFileName(
            parent, messages.text("create.jar.dialog_title"), "", messages.text("create.jar.dialog_filter")
        )
        return path or None

    return pick


class CreateServerDialog(FormDialog):
    """Collect the name, JAR and memory, then let the controller create the server.

    The folder follows the server name until the user edits it. The JAR comes from the
    download dialog or the file dialog, so it names an existing file when chosen. While
    the backend works every input is disabled and the dialog cannot be closed, because
    the copy cannot be cancelled.
    """

    def __init__(
        self,
        controller: ServerCreationController,
        messages: Messages,
        parent: QWidget | None = None,
        *,
        pick_jar: JarPicker | None = None,
        download_jar: JarPicker | None = None,
        system_memory_mb: int | None = None,
    ) -> None:
        """Build the form; ``pick_jar`` replaces the native file dialog in tests."""
        super().__init__(messages.text("create.title"), messages.text("create.subtitle"), parent)
        self.setObjectName("createServerDialog")
        self._controller = controller
        self._messages = messages
        self._pick_jar = pick_jar or pick_jar_with_system_dialog(messages)
        self._download_jar = download_jar
        self._source_jar = ""
        self._directory_follows_id = True
        self._attempted = False
        self.created_server_id: str | None = None
        self.field_errors: dict[str, QLabel] = {}
        self.field_hints: dict[str, QLabel] = {}
        self._system_memory_mb = system_memory_mb

        self._build()
        controller.state_changed.connect(self._on_state)
        controller.created.connect(self._on_created)
        controller.begin()
        self._refresh_validation()

    # --- construction -----------------------------------------------------------------------

    def _field(
        self, field: str, label_key: str, editor: QWidget, hint_key: str | None, *, focus: QWidget
    ) -> list[QWidget]:
        """Add a caption, the editor, a hint and an error line that replaces the hint when needed."""
        caption = QLabel(self._messages.text(label_key))
        caption.setObjectName("formLabel")
        caption.setBuddy(focus)
        focus.setAccessibleName(caption.text())
        hint = QLabel(self._messages.text(hint_key) if hint_key else "")
        hint.setObjectName("fieldHint")
        hint.setWordWrap(True)
        if hint_key:
            focus.setAccessibleDescription(hint.text())
        error = QLabel()
        error.setObjectName("fieldError")
        error.setWordWrap(True)
        error.hide()
        for widget in (caption, editor, hint, error):
            self.body.addWidget(widget)
        self.body.addSpacing(8)
        self.field_hints[field] = hint
        self.field_errors[field] = error
        return [caption, editor, hint, error]

    def _build(self) -> None:
        text = self._messages.text
        self.server_id_edit = QLineEdit()
        self.server_id_edit.setObjectName("serverIdInput")
        self.server_id_edit.setPlaceholderText(text("create.server_id.placeholder"))
        self.server_id_edit.textEdited.connect(self._on_server_id_edited)
        self._field(
            "server_id",
            "create.server_id.label",
            self.server_id_edit,
            "create.server_id.hint",
            focus=self.server_id_edit,
        )

        # Server software: download an official one, or use a JAR the user already has.
        self.download_button = button(text("create.jar.download"), "primary", "download")
        self.download_button.clicked.connect(self._on_download)
        self.download_button.setVisible(self._download_jar is not None)
        self.browse_button = button(text("create.jar.browse"), "secondary", "folder")
        self.browse_button.clicked.connect(self._on_browse)
        self.jar_icon = QLabel()
        self.jar_icon.setFixedSize(16, 16)
        # The chosen file, shown (not typed): it always comes from the download or the file dialog.
        self.jar_edit = QLabel(text("create.jar.placeholder"))
        self.jar_edit.setObjectName("jarName")
        self.jar_edit.setProperty("chosen", False)
        # The two ways side by side when they fit, one below the other otherwise (long texts, scaling);
        # the chosen file gets its own line, so nothing has to squeeze next to the buttons.
        if self._download_jar is not None:
            self.software_buttons: QWidget = WrapRow(self.download_button, self.browse_button, 8, fill=True)
        else:
            self.software_buttons = QWidget()
            only = QHBoxLayout(self.software_buttons)
            only.setContentsMargins(0, 0, 0, 0)
            only.addWidget(self.browse_button)
            only.addStretch(1)
        self.jar_edit.setWordWrap(True)
        chosen_row = QHBoxLayout()
        chosen_row.setContentsMargins(2, 0, 0, 0)
        chosen_row.setSpacing(8)
        chosen_row.addWidget(self.jar_icon, 0, Qt.AlignmentFlag.AlignTop)
        chosen_row.addWidget(self.jar_edit, 1)
        software = QWidget()
        software_layout = QVBoxLayout(software)
        software_layout.setContentsMargins(0, 0, 0, 0)
        software_layout.setSpacing(8)
        software_layout.addWidget(self.software_buttons)
        software_layout.addLayout(chosen_row)
        focus = self.download_button if self._download_jar is not None else self.browse_button
        self._field("source_jar", "create.source_jar.label", software, "create.source_jar.hint", focus=focus)

        self.memory_slider = MemorySlider(self._messages, self._system_memory_mb)
        self.memory_slider.changed.connect(lambda _value: self._refresh_validation())
        self._field("memory_mb", "create.memory_mb.label", self.memory_slider, None, focus=self.memory_slider.slider)
        self.field_hints["memory_mb"].hide()

        self.eula_check = QCheckBox(text("create.eula.label"))
        self.eula_check.setObjectName("eulaCheck")
        self.eula_check.toggled.connect(lambda _checked: self._refresh_validation())
        self.eula_check.setAccessibleDescription(text("create.eula.hint"))
        eula_hint = QLabel(text("create.eula.hint"))
        eula_hint.setObjectName("fieldHint")
        eula_hint.setWordWrap(True)
        eula_hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        eula_error = QLabel()
        eula_error.setObjectName("fieldError")
        eula_error.setWordWrap(True)
        eula_error.hide()
        for widget in (self.eula_check, eula_hint, eula_error):
            self.body.addWidget(widget)
        self.field_hints["eula"] = eula_hint
        self.field_errors["eula"] = eula_error

        # Advanced: the folder name (it follows the server name by default).
        self.advanced_button = button(text("create.advanced"), "ghost", "chevron-down")
        self.advanced_button.setCheckable(True)
        self.advanced_button.toggled.connect(self._show_advanced)
        self.body.addSpacing(6)
        self.body.addWidget(self.advanced_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.directory_edit = QLineEdit()
        self.directory_edit.setObjectName("directoryInput")
        self.directory_edit.setPlaceholderText(text("create.directory.placeholder"))
        self.directory_edit.textEdited.connect(self._on_directory_edited)
        self._advanced_widgets = self._field(
            "directory",
            "create.directory.label",
            self.directory_edit,
            "create.directory.hint",
            focus=self.directory_edit,
        )

        self.progress = QProgressBar()
        self.progress.setObjectName("creationProgress")
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        self.progress_label = QLabel(text("create.progress"))
        self.progress_label.setObjectName("fieldHint")
        self.progress_label.setWordWrap(True)
        self.progress_label.hide()
        self.error_banner = QLabel()
        self.error_banner.setObjectName("banner")
        self.error_banner.setProperty("tone", "error")
        self.error_banner.setWordWrap(True)
        self.error_banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.error_banner.hide()
        self.details_label = QLabel()
        self.details_label.setObjectName("errorDetails")
        self.details_label.setWordWrap(True)
        self.details_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_label.hide()
        for status in (self.progress, self.progress_label, self.error_banner, self.details_label):
            self.body.addWidget(status)

        self.cancel_button = secondary_button(text("create.cancel"))
        self.cancel_button.clicked.connect(self.reject)
        self.create_button = primary_button(text("create.submit"), "plus")
        self.create_button.clicked.connect(self._on_submit)
        self.add_buttons(self.cancel_button, self.create_button, default=self.create_button)
        self._show_advanced(False)
        self._show_jar()

    def _show_advanced(self, shown: bool) -> None:
        caption, editor = self._advanced_widgets[:2]
        hint, error = self.field_hints["directory"], self.field_errors["directory"]
        for widget in (caption, editor):
            widget.setVisible(shown)
        hint.setVisible(shown and not error.text())
        error.setVisible(shown and bool(error.text()))
        self.advanced_button.setIcon(icons.icon("chevron-up" if shown else "chevron-down", theme.TEXT_SECONDARY))

    def _show_jar(self) -> None:
        chosen = bool(self._source_jar)
        self.jar_icon.setPixmap(
            icons.pixmap("check" if chosen else "info", theme.ACCENT if chosen else theme.TEXT_MUTED)
        )

    # --- form ---------------------------------------------------------------------------------

    @property
    def memory_mb(self) -> int:
        """Return the memory the server will get, in megabytes."""
        return self.memory_slider.value_mb()

    def form(self) -> CreationForm:
        """Return the current input."""
        return CreationForm(
            server_id=self.server_id_edit.text(),
            directory=self.directory_edit.text(),
            source_jar=self._source_jar,
            memory_mb=self.memory_mb,
            eula_accepted=self.eula_check.isChecked(),
        )

    def _on_server_id_edited(self, value: str) -> None:
        if self._directory_follows_id:
            self.directory_edit.setText(value.strip())
        self._refresh_validation()

    def _on_directory_edited(self, value: str) -> None:
        self._directory_follows_id = value == "" or value == self.server_id_edit.text().strip()
        self._refresh_validation()

    def _on_download(self) -> None:
        if self._download_jar is not None:
            self._use_jar(self._download_jar(self))

    def _on_browse(self) -> None:
        self._use_jar(self._pick_jar(self))

    def _use_jar(self, path: str | None) -> None:
        if not path:
            return
        self._source_jar = path
        self.jar_edit.setText(PurePath(path).name)
        self.jar_edit.setToolTip(path)
        self.jar_edit.setProperty("chosen", True)
        repolish(self.jar_edit)
        self._show_jar()
        self._refresh_validation()

    def _refresh_validation(self) -> None:
        validation = self._controller.validate(self.form())
        touched = {
            "server_id": bool(self.server_id_edit.text()) or self._attempted,
            "directory": bool(self.directory_edit.text()) or self._attempted,
            "source_jar": bool(self._source_jar) or self._attempted,
            "memory_mb": True,
            "eula": self._attempted,
        }
        for field, label in self.field_errors.items():
            key = validation.errors.get(field)
            hint = self.field_hints[field]
            if key is not None and touched[field]:
                label.setText(self._error_text(field, key))
                if field == "directory" and not self.advanced_button.isChecked():
                    self.advanced_button.setChecked(True)  # a folder problem is never hidden
                label.show()
                hint.hide()
            else:
                label.clear()
                label.hide()
                hint.setVisible(bool(hint.text()) and (field != "directory" or self.advanced_button.isChecked()))
        self.create_button.setEnabled(validation.ok and not self._controller.busy)

    def _error_text(self, field: str, key: str) -> str:
        if key == "create.error.directory_taken":
            owner = self._controller.taken_directory_owner(self.directory_edit.text()) or ""
            return self._messages.text(key, server_id=owner)
        if key == "create.error.memory_range":
            return self._messages.text(key, minimum=MIN_MEMORY_MB, maximum=MAX_MEMORY_MB)
        return self._messages.text(key)

    # --- submission ---------------------------------------------------------------------------

    def _on_submit(self) -> None:
        self._attempted = True
        if not self._controller.submit(self.form()):
            self._refresh_validation()

    def _on_state(self, state: CreationState) -> None:
        busy = state.busy
        for widget in (
            self.server_id_edit,
            self.directory_edit,
            self.browse_button,
            self.download_button,
            self.memory_slider,
            self.eula_check,
            self.cancel_button,
            self.advanced_button,
        ):
            widget.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.progress_label.setVisible(busy)
        self.create_button.setText(self._messages.text("create.submitting" if busy else "create.submit"))
        if state.error is not None:
            self.error_banner.setText(self._messages.text(state.error.key, **state.error.params))
            self.details_label.setText(state.error.details)
            self.error_banner.show()
            self.details_label.setVisible(bool(state.error.details))
            repolish(self.error_banner)
        elif busy:
            self.error_banner.hide()
            self.details_label.hide()
        if busy:
            self.create_button.setEnabled(False)
        else:
            self._refresh_validation()

    def _on_created(self, configuration: ServerConfiguration) -> None:
        self.created_server_id = configuration.server_id
        self.accept()

    # --- closing ------------------------------------------------------------------------------

    def reject(self) -> None:
        """Cancel (also Escape) only before the operation starts; a running copy cannot be cancelled."""
        if self._controller.busy:
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Refuse to close while the backend is still working."""
        if self._controller.busy:
            event.ignore()
            return
        super().closeEvent(event)
