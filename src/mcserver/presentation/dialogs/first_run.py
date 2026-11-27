"""The first-run guide as a page: Java → servers folder → first server (M4-GUI-08)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from mcserver.presentation.controllers.first_run import Ending, FirstRunController, FirstRunState, Step
from mcserver.presentation.dialogs.form import FormDialog, primary_button, secondary_button
from mcserver.presentation.errors import render_message
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.widgets import Banner, button

JavaPicker = Callable[[QWidget], str | None]
FolderOpener = Callable[[Path], bool]


def _text(object_name: str = "fieldHint") -> QLabel:
    label = QLabel()
    label.setObjectName(object_name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _page() -> tuple[QWidget, QVBoxLayout]:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    return widget, layout


class FirstRunDialog(FormDialog):
    """One step at a time; Skip setup closes the guide, every step can be passed without changing anything."""

    def __init__(
        self,
        controller: FirstRunController,
        messages: Messages,
        pick_java: JavaPicker,
        open_folder: FolderOpener,
        parent: QWidget | None = None,
    ) -> None:
        """Show ``controller``'s guide; ``pick_java`` and ``open_folder`` use the system dialogs."""
        super().__init__(messages.text("first_run.title"), " ", parent, tone="info")
        self._controller = controller
        self._messages = messages
        self._pick_java = pick_java
        self._open_folder = open_folder
        text = messages.text

        self.step_title = _text("formLabel")
        self.body.addWidget(self.step_title)
        self.pages = QStackedWidget()
        self.body.addWidget(self.pages)

        # Java
        java_page, java = _page()
        self.java_intro = _text()
        self.java_intro.setText(text("first_run.java.intro"))
        self.java_banner = Banner()
        self.java_check_button = button(text("first_run.java.check"), "secondary", "restart")
        self.java_check_button.clicked.connect(controller.check_java)
        self.java_choose_button = button(text("first_run.java.choose"), "secondary", "java")
        self.java_choose_button.clicked.connect(self._choose_java)
        java_buttons = QHBoxLayout()
        java_buttons.addWidget(self.java_check_button)
        java_buttons.addWidget(self.java_choose_button)
        java_buttons.addStretch(1)
        for widget in (self.java_intro, self.java_banner):
            java.addWidget(widget)
        java.addLayout(java_buttons)
        java.addStretch(1)

        # Servers folder
        folder_page, folder = _page()
        self.folder_intro = _text()
        self.folder_intro.setText(text("first_run.folder.intro"))
        self.folder_path = _text("folderPath")
        self.folder_hint = _text()
        self.folder_hint.setText(text("first_run.folder.hint"))
        self.open_folder_button = button(text("first_run.folder.open"), "secondary", "folder")
        self.open_folder_button.clicked.connect(self._on_open_folder)
        self.folder_error = Banner()
        for widget in (self.folder_intro, self.folder_path, self.folder_hint):
            folder.addWidget(widget)
        folder.addWidget(self.open_folder_button, 0, Qt.AlignmentFlag.AlignLeft)
        folder.addWidget(self.folder_error)
        folder.addStretch(1)

        # First server
        create_page, create = _page()
        self.create_intro = _text()
        self.create_server_button = button(text("first_run.create.new"), "primary", "plus")
        self.create_server_button.clicked.connect(lambda: controller.finish(Ending.CREATE_SERVER))
        self.adopt_button = button(text("first_run.create.adopt"), "secondary", "import")
        self.adopt_button.clicked.connect(lambda: controller.finish(Ending.IMPORT_FOLDER))
        create_buttons = QHBoxLayout()
        create_buttons.addWidget(self.create_server_button)
        create_buttons.addWidget(self.adopt_button)
        create_buttons.addStretch(1)
        self.create_hint = _text()
        self.create_hint.setText(text("first_run.create.hint"))
        create.addWidget(self.create_intro)
        create.addLayout(create_buttons)
        create.addWidget(self.create_hint)
        create.addStretch(1)

        self._page_for = {Step.JAVA: java_page, Step.FOLDER: folder_page}
        self._page_for[Step.CREATE] = create_page
        for page in (java_page, folder_page, create_page):
            self.pages.addWidget(page)

        self.skip_button = secondary_button(text("first_run.skip"))
        self.skip_button.setObjectName("ghostButton")
        self.skip_button.clicked.connect(controller.skip)
        self.back_button = secondary_button(text("first_run.back"))
        self.back_button.clicked.connect(controller.back)
        self.next_button: QPushButton = primary_button(text("first_run.next"))
        self.next_button.clicked.connect(controller.next)
        self.add_buttons(self.back_button, self.next_button)
        self.footer_layout.insertWidget(0, self.skip_button)

        controller.state_changed.connect(self._show)
        controller.finished.connect(self._on_finished)
        self.finished.connect(self._disconnect)
        self._show(controller.state)

    def _disconnect(self) -> None:
        self._controller.state_changed.disconnect(self._show)
        self._controller.finished.disconnect(self._on_finished)

    def _show(self, state: FirstRunState) -> None:
        text = self._messages.text
        step = state.step
        if self.subtitle_label is not None:
            self.subtitle_label.setText(text("first_run.progress", number=state.index + 1, total=len(state.steps)))
        self.step_title.setText(text(f"first_run.{step.value}.title"))
        self.pages.setCurrentWidget(self._page_for[step])
        self._show_java(state)
        self.folder_path.setText(state.servers_root)
        has_servers = self._controller.has_servers
        self.create_intro.setText(text("first_run.create.has_servers" if has_servers else "first_run.create.intro"))
        movable = state.can_move
        self.back_button.setVisible(not state.is_first)
        self.back_button.setEnabled(movable)
        self.skip_button.setEnabled(movable)
        self.skip_button.setVisible(not state.is_last)
        self.next_button.setEnabled(movable)
        self.next_button.setText(text("first_run.finish" if state.is_last else "first_run.next"))

    def _show_java(self, state: FirstRunState) -> None:
        text = self._messages.text
        status = state.java
        if state.java_error is not None:
            self.java_banner.show_message(render_message(self._messages, state.java_error), "error")
        elif status is None:
            self.java_banner.show_message(text("first_run.java.unknown"), "info")
        elif status.installation is not None:
            installation = status.installation
            self.java_banner.show_message(
                text("first_run.java.found", major=installation.major_version, path=installation.executable),
                "success",
            )
        else:
            self.java_banner.show_message(text("first_run.java.missing"), "notice")
        available = status is not None
        self.java_check_button.setEnabled(available)
        self.java_choose_button.setEnabled(available)

    def _choose_java(self) -> None:
        path = self._pick_java(self)
        if path:
            self._controller.choose_java(path)

    def _on_open_folder(self) -> None:
        path = self._controller.state.servers_root
        if self._open_folder(Path(path)):
            self.folder_error.clear()
        else:
            self.folder_error.show_message(self._messages.text("dashboard.open_folder_failed", path=path), "error")

    def _on_finished(self, _ending: Ending) -> None:
        self.accept()

    def reject(self) -> None:
        """Escape or closing the dialog skips the guide."""
        if self._controller.state.finished is not None:
            super().reject()
            return
        self._controller.skip()


__all__ = ["FirstRunDialog"]
