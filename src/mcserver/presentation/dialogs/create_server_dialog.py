"""Modal dialog for creating a server from a JAR the user already has."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePath

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mcserver.domain.server_configuration import MAX_MEMORY_MB, MIN_MEMORY_MB, ServerConfiguration
from mcserver.presentation import theme
from mcserver.presentation.controllers.server_creation import (
    DEFAULT_MEMORY_MB,
    CreationForm,
    CreationState,
    ServerCreationController,
)
from mcserver.presentation.i18n import Messages

JarPicker = Callable[[QWidget], str | None]

MEMORY_STEP_MB = 512


def pick_jar_with_system_dialog(messages: Messages) -> JarPicker:
    """Return a picker that opens the native "open file" dialog for ``.jar`` files."""

    def pick(parent: QWidget) -> str | None:
        path, _filter = QFileDialog.getOpenFileName(
            parent, messages.text("create.jar.dialog_title"), "", messages.text("create.jar.dialog_filter")
        )
        return path or None

    return pick


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


class CreateServerDialog(QDialog):
    """Collect ID, folder, JAR and memory, then let the controller create the server.

    The folder follows the server ID until the user edits it. The JAR can only
    be chosen with the file dialog, so the path always names an existing file
    at selection time. While the backend works, every input is disabled and the
    dialog cannot be closed, because the copy cannot be cancelled.
    """

    def __init__(
        self,
        controller: ServerCreationController,
        messages: Messages,
        parent: QWidget | None = None,
        *,
        pick_jar: JarPicker | None = None,
    ) -> None:
        """Build the form; ``pick_jar`` replaces the native file dialog in tests."""
        super().__init__(parent)
        self.setObjectName("createServerDialog")
        self.setWindowTitle(messages.text("create.title"))
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setStyleSheet(theme.STYLESHEET)
        self._controller = controller
        self._messages = messages
        self._pick_jar = pick_jar or pick_jar_with_system_dialog(messages)
        self._source_jar = ""
        self._directory_follows_id = True
        self._attempted = False
        self.created_server_id: str | None = None

        self._build()
        controller.state_changed.connect(self._on_state)
        controller.created.connect(self._on_created)
        controller.begin()
        self._refresh_validation()

    # --- construction ---------------------------------------------------------------------

    def _build(self) -> None:
        messages = self._messages
        title = QLabel(messages.text("create.title"))
        title.setObjectName("dialogTitle")
        subtitle = QLabel(messages.text("create.subtitle"))
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)

        self.server_id_edit = QLineEdit()
        self.server_id_edit.setObjectName("serverIdInput")
        self.server_id_edit.setPlaceholderText(messages.text("create.server_id.placeholder"))
        self.server_id_edit.textEdited.connect(self._on_server_id_edited)

        self.directory_edit = QLineEdit()
        self.directory_edit.setObjectName("directoryInput")
        self.directory_edit.setPlaceholderText(messages.text("create.directory.placeholder"))
        self.directory_edit.textEdited.connect(self._on_directory_edited)

        self.jar_edit = QLineEdit()
        self.jar_edit.setObjectName("jarInput")
        self.jar_edit.setReadOnly(True)
        self.jar_edit.setPlaceholderText(messages.text("create.jar.placeholder"))
        self.browse_button = QPushButton(messages.text("create.jar.browse"))
        self.browse_button.setObjectName("secondaryButton")
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_button.clicked.connect(self._on_browse)
        jar_row = QHBoxLayout()
        jar_row.setSpacing(8)
        jar_row.addWidget(self.jar_edit, 1)
        jar_row.addWidget(self.browse_button)

        self.memory_spin = QSpinBox()
        self.memory_spin.setObjectName("memoryInput")
        self.memory_spin.setRange(MIN_MEMORY_MB, MAX_MEMORY_MB)
        self.memory_spin.setSingleStep(MEMORY_STEP_MB)
        self.memory_spin.setValue(DEFAULT_MEMORY_MB)
        self.memory_spin.setSuffix(messages.text("create.memory.suffix"))
        # Keep the step buttons: with a stylesheet, Qt collapses a button-less spin box's editor.
        self.memory_spin.valueChanged.connect(lambda _value: self._refresh_validation())

        self.field_errors: dict[str, QLabel] = {}
        self.field_hints: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(4)
        rows = (
            ("server_id", self.server_id_edit),
            ("directory", self.directory_edit),
            ("source_jar", jar_row),
            ("memory_mb", self.memory_spin),
        )
        row_index = 0
        for field, editor in rows:
            label = QLabel(messages.text(f"create.{field}.label"))
            label.setObjectName("formLabel")
            hint = QLabel(messages.text(f"create.{field}.hint"))
            hint.setObjectName("fieldHint")
            hint.setWordWrap(True)
            error = QLabel()
            error.setObjectName("fieldError")
            error.setWordWrap(True)
            error.hide()
            self.field_hints[field] = hint
            self.field_errors[field] = error
            grid.addWidget(label, row_index, 0)
            if isinstance(editor, QHBoxLayout):
                grid.addLayout(editor, row_index + 1, 0)
            else:
                grid.addWidget(editor, row_index + 1, 0)
            grid.addWidget(hint, row_index + 2, 0)
            grid.addWidget(error, row_index + 3, 0)
            grid.setRowMinimumHeight(row_index + 4, 10)
            row_index += 5

        self.progress = QProgressBar()
        self.progress.setObjectName("creationProgress")
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        self.progress_label = QLabel(messages.text("create.progress"))
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

        self.cancel_button = QPushButton(messages.text("create.cancel"))
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.clicked.connect(self.reject)
        self.create_button = QPushButton(messages.text("create.submit"))
        self.create_button.setObjectName("primaryButton")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._on_submit)
        for button in (self.cancel_button, self.create_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.create_button)

        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 28, 32, 28)
        card_layout.setSpacing(10)
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(12)
        card_layout.addLayout(grid)
        card_layout.addWidget(self.progress)
        card_layout.addWidget(self.progress_label)
        card_layout.addWidget(self.error_banner)
        card_layout.addWidget(self.details_label)
        card_layout.addSpacing(8)
        card_layout.addLayout(buttons)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)

    # --- form ------------------------------------------------------------------------------

    def form(self) -> CreationForm:
        """Return the current input."""
        return CreationForm(
            server_id=self.server_id_edit.text(),
            directory=self.directory_edit.text(),
            source_jar=self._source_jar,
            memory_mb=self.memory_spin.value(),
        )

    def _on_server_id_edited(self, text: str) -> None:
        if self._directory_follows_id:
            self.directory_edit.setText(text.strip())
        self._refresh_validation()

    def _on_directory_edited(self, text: str) -> None:
        self._directory_follows_id = text == "" or text == self.server_id_edit.text().strip()
        self._refresh_validation()

    def _on_browse(self) -> None:
        path = self._pick_jar(self)
        if not path:
            return
        self._source_jar = path
        self.jar_edit.setText(PurePath(path).name)
        self.jar_edit.setToolTip(path)
        self._refresh_validation()

    def _refresh_validation(self) -> None:
        validation = self._controller.validate(self.form())
        touched = {
            "server_id": bool(self.server_id_edit.text()) or self._attempted,
            "directory": bool(self.directory_edit.text()) or self._attempted,
            "source_jar": bool(self._source_jar) or self._attempted,
            "memory_mb": True,
        }
        for field, label in self.field_errors.items():
            key = validation.errors.get(field)
            if key is not None and touched[field]:
                label.setText(self._error_text(field, key))
                label.show()
                self.field_hints[field].hide()
            else:
                label.hide()
                self.field_hints[field].show()
        self.create_button.setEnabled(validation.ok and not self._controller.busy)

    def _error_text(self, field: str, key: str) -> str:
        if key == "create.error.directory_taken":
            owner = self._controller.taken_directory_owner(self.directory_edit.text()) or ""
            return self._messages.text(key, server_id=owner)
        if key == "create.error.memory_range":
            return self._messages.text(key, minimum=MIN_MEMORY_MB, maximum=MAX_MEMORY_MB)
        return self._messages.text(key)

    # --- submission ------------------------------------------------------------------------

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
            self.memory_spin,
            self.cancel_button,
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
            _repolish(self.error_banner)
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

    # --- closing ---------------------------------------------------------------------------

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
