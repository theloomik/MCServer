"""Loads configured servers and the selected server for the main window."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, Signal

from mcserver.application.errors import ServerConfigurationNotFound, ServerConfigurationStorageError
from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_management import ServerManagement
from mcserver.domain.lifecycle import ServerState
from mcserver.domain.server_configuration import ServerConfiguration

_logger = logging.getLogger(__name__)


class ServerStatus(Enum):
    """What the GUI can honestly say about a server's process."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    UNKNOWN = "unknown"
    """No coordinator (Java missing), so this application cannot tell."""


_STATE_TO_STATUS = {
    ServerState.STOPPED: ServerStatus.STOPPED,
    ServerState.STARTING: ServerStatus.STARTING,
    ServerState.RUNNING: ServerStatus.RUNNING,
    ServerState.STOPPING: ServerStatus.STOPPING,
    ServerState.KILLING: ServerStatus.STOPPING,
}


@dataclass(frozen=True, slots=True)
class ServerRow:
    """A configured server as shown in the list and the details panel."""

    configuration: ServerConfiguration
    status: ServerStatus

    @property
    def server_id(self) -> str:
        """Return the server identifier."""
        return self.configuration.server_id


@dataclass(frozen=True, slots=True)
class ServerListState:
    """Everything the list and details views need to render."""

    servers: tuple[ServerRow, ...] = ()
    selected: ServerRow | None = None
    list_error_key: str | None = None
    """Message key when the list could not be loaded."""
    details_error_key: str | None = None
    """Message key when the selected server could not be shown."""


class ServerListController(QObject):
    """Read servers through ``ServerManagement`` and report one state snapshot per change.

    Status comes from the coordinator of this application only: a server is
    ``RUNNING`` etc. while it is the coordinator's active server and
    ``STOPPED`` otherwise. Without a coordinator (Java missing) every status is
    ``UNKNOWN``. Reads are synchronous; the configuration file is small and local.
    """

    state_changed = Signal(object)  # ServerListState

    def __init__(
        self, management: ServerManagement, coordinator: ServerCoordinator | None, parent: QObject | None = None
    ) -> None:
        """Use ``management`` for configurations and ``coordinator`` (optional) for status."""
        super().__init__(parent)
        self._management = management
        self._coordinator = coordinator
        self._state = ServerListState()

    @property
    def state(self) -> ServerListState:
        """Return the latest snapshot."""
        return self._state

    def refresh(self) -> None:
        """Reload all servers, keeping the selection if the server still exists."""
        previous = self._state.selected.server_id if self._state.selected else None
        try:
            configurations = self._management.list_servers()
        except ServerConfigurationStorageError:
            _logger.exception("Could not load the server list.")
            self._publish(ServerListState(list_error_key="server_list.error.load"))
            return
        servers = tuple(self._row(configuration) for configuration in configurations)
        self._state = ServerListState(servers=servers)
        if previous is not None and any(row.server_id == previous for row in servers):
            self.select(previous)
        else:
            self._publish(self._state)

    def select(self, server_id: str | None) -> None:
        """Show ``server_id``'s current configuration, or clear the selection with ``None``."""
        if server_id is None:
            self._publish(ServerListState(servers=self._state.servers, list_error_key=self._state.list_error_key))
            return
        try:
            configuration = self._management.get_server(server_id)
        except ServerConfigurationNotFound:
            _logger.info("Selected server %r no longer exists.", server_id)
            self._publish(ServerListState(servers=self._state.servers, details_error_key="server_details.error.gone"))
            return
        except ServerConfigurationStorageError:
            _logger.exception("Could not load server %r.", server_id)
            self._publish(ServerListState(servers=self._state.servers, details_error_key="server_details.error.load"))
            return
        row = self._row(configuration)
        servers = tuple(row if existing.server_id == server_id else existing for existing in self._state.servers)
        self._publish(ServerListState(servers=servers, selected=row))

    def _row(self, configuration: ServerConfiguration) -> ServerRow:
        return ServerRow(configuration=configuration, status=self._status(configuration.server_id))

    def _status(self, server_id: str) -> ServerStatus:
        if self._coordinator is None:
            return ServerStatus.UNKNOWN
        if self._coordinator.active_server_id != server_id:
            return ServerStatus.STOPPED
        return _STATE_TO_STATUS[self._coordinator.state]

    def _publish(self, state: ServerListState) -> None:
        self._state = state
        self.state_changed.emit(state)
