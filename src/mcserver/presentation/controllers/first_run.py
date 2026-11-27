"""The first-run guide: Java, servers folder, first server (M4-GUI-08)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum

from PySide6.QtCore import QObject, Signal

from mcserver.application.java_setup import JavaSetup, JavaStatus
from mcserver.application.settings import SettingsService
from mcserver.presentation.errors import UserMessage, describe_error

_logger = logging.getLogger(__name__)


class Step(str, Enum):
    """One page of the guide; the GUI shows ``first_run.<value>.*`` texts."""

    JAVA = "java"
    FOLDER = "folder"
    CREATE = "create"


class Ending(str, Enum):
    """What the user chose on the last page."""

    DONE = "done"
    CREATE_SERVER = "create_server"
    IMPORT_FOLDER = "import_folder"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class FirstRunState:
    """What the guide shows."""

    steps: tuple[Step, ...] = (Step.JAVA, Step.FOLDER, Step.CREATE)
    index: int = 0
    servers_root: str = ""
    java: JavaStatus | None = None
    """``None`` when Java cannot be checked here (no Java service)."""
    java_error: UserMessage | None = None
    finished: Ending | None = None

    @property
    def step(self) -> Step:
        """Return the shown step."""
        return self.steps[self.index]

    @property
    def is_first(self) -> bool:
        """Return whether Back is unavailable."""
        return self.index == 0

    @property
    def is_last(self) -> bool:
        """Return whether Next becomes Finish."""
        return self.index == len(self.steps) - 1

    @property
    def can_move(self) -> bool:
        """Return whether Back/Next/Skip may be used."""
        return self.finished is None


class FirstRunController(QObject):
    """Drive the guide; every step can be skipped and nothing is changed without the user's action."""

    state_changed = Signal(object)  # FirstRunState
    finished = Signal(object)  # Ending

    def __init__(
        self,
        servers_root: str,
        java: JavaSetup | None,
        settings: SettingsService | None,
        server_count: Callable[[], int],
        parent: QObject | None = None,
    ) -> None:
        """Use ``settings`` to remember that the guide ran."""
        super().__init__(parent)
        self._java = java
        self._settings = settings
        self._server_count = server_count
        self._state = FirstRunState(servers_root=servers_root)

    @staticmethod
    def should_run(settings: SettingsService | None, server_count: int) -> bool:
        """Return whether to show the guide at startup: never completed and no servers yet."""
        if settings is None:
            return False
        return not settings.current.first_run_completed and server_count == 0

    @property
    def state(self) -> FirstRunState:
        """Return the current state."""
        return self._state

    @property
    def has_servers(self) -> bool:
        """Return whether there is at least one server."""
        return self._server_count() > 0

    def start(self) -> None:
        """Read Java, then show the first step."""
        self._publish(replace(self._state, index=0, java=self._status()))

    def next(self) -> None:
        """Go to the next step, or finish on the last one."""
        if not self._state.can_move:
            return
        if self._state.is_last:
            self.finish(Ending.DONE)
            return
        self._publish(replace(self._state, index=self._state.index + 1))

    def back(self) -> None:
        """Go to the previous step."""
        if self._state.can_move and not self._state.is_first:
            self._publish(replace(self._state, index=self._state.index - 1))

    def check_java(self) -> None:
        """Detect Java again (it may have been installed meanwhile)."""
        self._publish(replace(self._state, java=self._status(), java_error=None))

    def choose_java(self, executable: str) -> None:
        """Use ``executable`` from now on (stored in the settings when they are available)."""
        try:
            if self._settings is not None:
                self._settings.update(java_executable=executable)
            elif self._java is not None:
                self._java.choose_executable(executable)
        except Exception as error:
            self._publish(replace(self._state, java_error=describe_error(error)))
            return
        self.check_java()

    def finish(self, ending: Ending = Ending.DONE) -> None:
        """Remember that the guide ran and tell the window what to open next."""
        if self._state.finished is not None:
            return
        if self._settings is not None:
            try:
                self._settings.update(first_run_completed=True)
            except Exception:
                _logger.warning("Could not save that the first-run guide finished.", exc_info=True)
        self._publish(replace(self._state, finished=ending))
        self.finished.emit(ending)

    def skip(self) -> None:
        """Close the guide now; it can be opened again from Settings."""
        self.finish(Ending.SKIPPED)

    def _status(self) -> JavaStatus | None:
        if self._java is None:
            return None
        try:
            return self._java.status()
        except Exception:
            _logger.warning("Could not check Java for the first-run guide.", exc_info=True)
            return None

    def _publish(self, state: FirstRunState) -> None:
        self._state = state
        self.state_changed.emit(state)


__all__ = ["Ending", "FirstRunController", "FirstRunState", "Step"]
