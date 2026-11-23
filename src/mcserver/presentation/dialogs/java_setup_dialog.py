"""Guidance when Java is missing or too old: install it, choose java.exe, or (too old) start anyway."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLabel, QWidget

from mcserver.application.errors import InvalidJavaExecutable, JavaNotFound, JavaVersionTooOld
from mcserver.application.java_setup import JavaSetup, JavaStatus
from mcserver.presentation.dialogs.form import FormDialog, danger_button, primary_button, secondary_button
from mcserver.presentation.errors import describe_error, render_message
from mcserver.presentation.i18n import Messages
from mcserver.presentation.views.widgets import button

JavaPicker = Callable[[QWidget], "str | None"]


class JavaChoice(Enum):
    """How the dialog was closed."""

    CANCELLED = "cancelled"
    RETRY = "retry"
    """Java was found or chosen; try the start again."""
    START_ANYWAY = "start_anyway"
    """Start despite a too-old Java (the user accepted that it will probably fail)."""


def pick_java_with_system_dialog(messages: Messages) -> JavaPicker:
    """Return a picker that asks for ``java.exe`` with the system file dialog."""

    def pick(parent: QWidget) -> str | None:
        path, _filter = QFileDialog.getOpenFileName(
            parent, messages.text("java.choose.dialog_title"), "", messages.text("java.choose.filter")
        )
        return path or None

    return pick


class JavaSetupDialog(FormDialog):
    """Explain the Java problem and offer: Check again, Choose java.exe…, (too old) Start anyway, Cancel.

    Java checks run synchronously: ``java -version`` returns within seconds and
    the user is waiting on this dialog anyway.
    """

    def __init__(
        self,
        problem: JavaNotFound | JavaVersionTooOld,
        java: JavaSetup,
        messages: Messages,
        parent: QWidget | None = None,
        *,
        pick_java: JavaPicker | None = None,
    ) -> None:
        """Build the dialog for ``problem``."""
        super().__init__(messages.text("java.dialog.title"), "", parent, tone="warning")
        self._problem = problem
        self._java = java
        self._messages = messages
        self._pick_java = pick_java or pick_java_with_system_dialog(messages)
        self.choice = JavaChoice.CANCELLED

        self.explanation = QLabel(self._explanation())
        self.explanation.setObjectName("dialogSubtitle")
        self.explanation.setWordWrap(True)
        self.explanation.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status_label = QLabel()
        self.status_label.setObjectName("controlHint")
        self.status_label.setWordWrap(True)
        self.body.addWidget(self.explanation)
        self.body.addWidget(self.status_label)

        self.check_button = secondary_button(messages.text("java.check"), "restart")
        self.check_button.clicked.connect(self.check_again)
        self.choose_button = primary_button(messages.text("java.choose"), "java")
        self.choose_button.clicked.connect(self.choose_executable)
        self.start_anyway_button = danger_button(messages.text("java.start_anyway"))
        self.start_anyway_button.clicked.connect(self._start_anyway)
        self.start_anyway_button.setVisible(isinstance(problem, JavaVersionTooOld))
        cancel = button(messages.text("java.cancel"), "ghost")
        cancel.clicked.connect(self.reject)
        self.add_buttons(cancel, self.start_anyway_button, self.check_button, self.choose_button)

    def _explanation(self) -> str:
        problem = self._problem
        if isinstance(problem, JavaVersionTooOld):
            return self._messages.text(
                "java.too_old.text",
                server_id=problem.server_id,
                required=problem.required_major,
                found=problem.found_major,
                executable=problem.executable,
            )
        needed = self._messages.text("java.needed", required=problem.required_major) if problem.required_major else ""
        return self._messages.text("java.missing.text", needed=needed)

    def check_again(self) -> None:
        """Detect Java now; close for a retry when a suitable one is found."""
        self._accept_if_suitable(self._java.status())

    def choose_executable(self) -> None:
        """Let the user pick ``java.exe``; use it for later starts if it runs."""
        path = self._pick_java(self)
        if not path:
            return
        try:
            status = self._java.choose_executable(path)
        except InvalidJavaExecutable as error:
            self.status_label.setText(render_message(self._messages, describe_error(error)))
            return
        self._accept_if_suitable(status)

    def _accept_if_suitable(self, status: JavaStatus) -> None:
        installation = status.installation
        if installation is None:
            self.status_label.setText(self._messages.text("errors.java_not_found"))
            return
        self.status_label.setText(
            self._messages.text("java.found", major=installation.major_version, executable=installation.executable)
        )
        required = getattr(self._problem, "required_major", None)
        if required is None or installation.major_version >= required:
            self.choice = JavaChoice.RETRY
            self.accept()

    def _start_anyway(self) -> None:
        self.choice = JavaChoice.START_ANYWAY
        self.accept()
