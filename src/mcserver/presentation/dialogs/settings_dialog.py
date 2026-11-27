"""Application settings as a page: appearance, Java, servers and help (UX overhaul)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mcserver.application.errors import InvalidJavaExecutable
from mcserver.application.java_setup import JavaSetup
from mcserver.application.settings import (
    STARTUP_TIMEOUT_RANGE,
    STOP_TIMEOUT_RANGE,
    SUPPORTED_THEMES,
    ApplicationSettings,
)
from mcserver.presentation import icons, theme
from mcserver.presentation.controllers.server_management import ManagementController
from mcserver.presentation.dialogs.edit_server_dialog import JavaPicker, pick_java_with_system_dialog
from mcserver.presentation.dialogs.form import FormDialog, primary_button, secondary_button
from mcserver.presentation.errors import describe_error, render_message
from mcserver.presentation.i18n import Messages, available_languages
from mcserver.presentation.views.widgets import button, repolish

FolderOpener = Callable[[Path], bool]
CONTROL_WIDTH = 240


def _text(object_name: str, text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    return label


class SettingsDialog(FormDialog):
    """Show and change application settings; the Java choice is checked before it is saved."""

    setup_guide_requested = Signal()

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
        """Build the page from the current ``settings``."""
        super().__init__(messages.text("settings.title"), messages.text("settings.subtitle"), parent)
        self.setObjectName("settingsPage")
        self._controller = controller
        self._java = java
        self._messages = messages
        self._open_folder = open_folder
        self._pick_java = pick_java or pick_java_with_system_dialog(messages)
        self._java_executable = settings.java_executable
        text = messages.text

        # Appearance
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(text("settings.theme.auto"), None)
        for name in SUPPORTED_THEMES:
            self.theme_combo.addItem(text(f"settings.theme.{name}"), name)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(settings.theme)))
        self.language_combo = QComboBox()
        self.language_combo.addItem(text("settings.language.auto"), None)
        for code in available_languages():
            self.language_combo.addItem(text(f"settings.language.{code}"), code)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(settings.language)))
        appearance = self._section("settings.section.appearance", "sliders")
        self._row(appearance, "settings.theme.label", "settings.theme.hint", self.theme_combo)
        self._row(appearance, "settings.language.label", "settings.language.hint", self.language_combo)

        # Java
        java_section = self._section("settings.section.java", "java")
        self.java_status = _text("settingStatus")
        self.java_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.java_status_icon = QLabel()
        self.java_status_icon.setFixedSize(16, 16)
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.addWidget(self.java_status_icon, 0, Qt.AlignmentFlag.AlignTop)
        status_row.addWidget(self.java_status, 1)
        self.java_label = _text("fieldHint")
        self.java_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.java_check = button(text("settings.java.check"), "secondary", "restart")
        self.java_check.clicked.connect(self.refresh_java)
        self.java_choose = button(text("settings.java.choose"), "secondary", "java")
        self.java_choose.clicked.connect(self.choose_java)
        self.java_auto = button(text("settings.java.auto"), "ghost")
        self.java_auto.clicked.connect(self.use_automatic_java)
        java_buttons = QHBoxLayout()
        java_buttons.setSpacing(8)
        for widget in (self.java_check, self.java_choose, self.java_auto):
            java_buttons.addWidget(widget)
        java_buttons.addStretch(1)
        java_box = QVBoxLayout()
        java_box.setContentsMargins(16, 14, 16, 14)
        java_box.setSpacing(8)
        java_box.addLayout(status_row)
        java_box.addWidget(self.java_label)
        java_box.addLayout(java_buttons)
        java_section.addLayout(java_box)
        for widget in (self.java_check, self.java_choose, self.java_auto):
            widget.setEnabled(java is not None)

        # Servers
        servers = self._section("settings.section.servers", "server")
        self.folder_label = _text("monoValue", str(controller.servers_root))
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.open_folder_button = button(text("settings.open_folder"), "secondary", "folder")
        self.open_folder_button.clicked.connect(self._open)
        folder_box = QWidget()
        folder_layout = QHBoxLayout(folder_box)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.addWidget(self.open_folder_button)
        self._row(servers, "settings.servers_folder", None, folder_box, value=self.folder_label)
        self.stop_spin = self._seconds(STOP_TIMEOUT_RANGE, settings.stop_timeout_seconds)
        self._row(servers, "settings.stop_timeout.label", "settings.stop_timeout.hint", self.stop_spin)
        self.startup_spin = self._seconds(STARTUP_TIMEOUT_RANGE, settings.startup_timeout_seconds)
        self._row(servers, "settings.startup_timeout.label", "settings.startup_timeout.hint", self.startup_spin)
        self.auto_restart_check = QCheckBox()
        self.auto_restart_check.setChecked(settings.auto_restart)
        self._row(servers, "settings.auto_restart.label", "settings.auto_restart.hint", self.auto_restart_check)

        # Help
        help_section = self._section("settings.section.help", "info")
        self.setup_guide_button = button(text("settings.setup_guide"), "secondary")
        self.setup_guide_button.clicked.connect(self.setup_guide_requested)
        self._row(help_section, "settings.setup_guide.label", "settings.setup_guide.hint", self.setup_guide_button)

        self.cancel_button = secondary_button(text("settings.cancel"))
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = primary_button(text("settings.save"), "check")
        self.save_button.clicked.connect(self.save)
        self.add_buttons(self.cancel_button, self.save_button)
        self._show_java()

    # --- layout helpers -------------------------------------------------------------------------

    def _section(self, title_key: str, icon_name: str) -> QVBoxLayout:
        """Add a titled group; return the layout its rows go into."""
        heading = QHBoxLayout()
        heading.setSpacing(8)
        tile = QLabel()
        tile.setPixmap(icons.pixmap(icon_name, theme.TEXT_SECONDARY, 16))
        tile.setFixedSize(16, 16)
        caption = QLabel(self._messages.text(title_key))
        caption.setObjectName("settingsSection")
        heading.addWidget(tile)
        heading.addWidget(caption, 1)
        self.body.addSpacing(6)
        self.body.addLayout(heading)
        group = QFrame()
        group.setObjectName("settingsGroup")
        rows = QVBoxLayout(group)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)
        self.body.addWidget(group)
        return rows

    def _row(
        self,
        rows: QVBoxLayout,
        title_key: str,
        hint_key: str | None,
        control: QWidget,
        *,
        value: QLabel | None = None,
    ) -> None:
        """Add one setting: title and description on the left, its control on the right."""
        row = QFrame()
        row.setObjectName("settingsRow")
        row.setProperty("first", rows.count() == 0)
        repolish(row)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = _text("settingTitle", self._messages.text(title_key))
        title.setBuddy(control)
        texts.addWidget(title)
        if value is not None:
            texts.addWidget(value)
        if hint_key is not None:
            hint = _text("fieldHint", self._messages.text(hint_key))
            texts.addWidget(hint)
            control.setAccessibleDescription(hint.text())
        control.setAccessibleName(title.text())
        layout.addLayout(texts, 1)
        if isinstance(control, (QComboBox, QSpinBox)):
            control.setFixedWidth(CONTROL_WIDTH)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        rows.addWidget(row)

    def _seconds(self, limits: tuple[int, int], value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(*limits)
        spin.setSingleStep(10)
        spin.setSuffix(self._messages.text("settings.seconds"))
        spin.setValue(value)
        return spin

    # --- behaviour ------------------------------------------------------------------------------

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

    def refresh_java(self) -> None:
        """Detect Java again (it may have been installed meanwhile) and show the result."""
        self._show_java()

    def save(self) -> None:
        """Store the settings; close on success."""
        error = self._controller.update_settings(
            java_executable=self._java_executable,
            stop_timeout_seconds=self.stop_spin.value(),
            startup_timeout_seconds=self.startup_spin.value(),
            auto_restart=self.auto_restart_check.isChecked(),
            language=self.language_combo.currentData(),
            theme=self.theme_combo.currentData(),
        )
        if error is not None:
            self.show_error(render_message(self._messages, error))
            return
        self.accept()

    def _show_java(self) -> None:
        """Show which Java starts servers and whether it works."""
        text = self._messages.text
        self.java_label.setText(
            text("settings.java.custom", path=self._java_executable)
            if self._java_executable
            else text("settings.java.automatic_hint")
        )
        ready: bool | None = None
        if self._java is None:
            message = text("settings.java.unknown")
        elif self._java_executable:
            try:
                installation = self._java.check(self._java_executable)
            except InvalidJavaExecutable:
                ready, message = False, text("settings.java.invalid")
            else:
                ready, message = True, text("settings.java.found", major=installation.major_version)
        else:
            detected = self._java.status().installation
            if detected is None:
                ready, message = False, text("settings.java.missing")
            else:
                ready = True
                message = text("settings.java.found_at", major=detected.major_version, path=detected.executable)
        self.java_status.setText(message)
        color = theme.TEXT_MUTED if ready is None else (theme.ACCENT if ready else theme.WARNING_TEXT)
        self.java_status_icon.setPixmap(icons.pixmap("check" if ready else "alert", color, 16))
        self.java_status.setProperty("tone", "unknown" if ready is None else ("ok" if ready else "problem"))
        repolish(self.java_status)

    def _open(self) -> None:
        if self._open_folder is not None:
            self._open_folder(self._controller.servers_root)
