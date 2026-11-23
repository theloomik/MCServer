"""Load and save the selected server's ``server.properties`` (M3-GUI-02)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from mcserver.application.server_properties import ServerPropertiesService
from mcserver.domain.server_properties import InvalidServerProperties
from mcserver.presentation.errors import UserMessage, describe_error


@dataclass(frozen=True, slots=True)
class PropertiesState:
    """What the properties editor shows."""

    server_id: str | None = None
    values: Mapping[str, str] = field(default_factory=dict)
    exists: bool = True
    problems: Mapping[str, str] = field(default_factory=dict)
    """Invalid values by key, from the last save attempt."""
    message: UserMessage | None = None
    tone: str = "notice"


class PropertiesController(QObject):
    """Read and write through ``ServerPropertiesService``; file access is fast, so it runs on the GUI thread."""

    state_changed = Signal(object)  # PropertiesState

    def __init__(self, service: ServerPropertiesService | None, parent: QObject | None = None) -> None:
        """Use ``service`` (``None`` disables the editor)."""
        super().__init__(parent)
        self._service = service
        self._state = PropertiesState()

    @property
    def available(self) -> bool:
        """Return whether properties can be edited at all."""
        return self._service is not None

    @property
    def state(self) -> PropertiesState:
        """Return the current state."""
        return self._state

    def show_server(self, server_id: str | None) -> None:
        """Load the properties of ``server_id`` (``None`` clears the editor)."""
        if server_id == self._state.server_id and server_id is not None:
            return
        self.reload(server_id)

    def reload(self, server_id: str | None = None) -> None:
        """Read the file again, dropping unsaved edits."""
        target = server_id if server_id is not None else self._state.server_id
        if target is None or self._service is None:
            self._publish(PropertiesState())
            return
        try:
            view = self._service.load(target)
        except Exception as error:
            self._publish(PropertiesState(server_id=target, message=describe_error(error), tone="error"))
            return
        self._publish(PropertiesState(server_id=target, values=view.values, exists=view.exists))

    def save(self, changes: Mapping[str, str]) -> bool:
        """Store ``changes``; return whether they were saved (invalid values are listed in the state)."""
        state = self._state
        if self._service is None or state.server_id is None:
            return False
        changed = {key: value for key, value in changes.items() if state.values.get(key) != value}
        try:
            restart_needed = self._service.save(state.server_id, changed)
        except InvalidServerProperties as error:
            self._publish(
                PropertiesState(
                    state.server_id,
                    state.values,
                    state.exists,
                    error.problems,
                    UserMessage("properties.invalid"),
                    "error",
                )
            )
            return False
        except Exception as error:
            self._publish(
                PropertiesState(state.server_id, state.values, state.exists, {}, describe_error(error), "error")
            )
            return False
        view = self._service.load(state.server_id)
        key = "properties.saved_restart" if restart_needed else "properties.saved"
        self._publish(PropertiesState(state.server_id, view.values, view.exists, {}, UserMessage(key), "success"))
        return True

    def _publish(self, state: PropertiesState) -> None:
        self._state = state
        self.state_changed.emit(state)
