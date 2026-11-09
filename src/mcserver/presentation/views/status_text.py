"""Message keys for server statuses, shared by the list and details views."""

from mcserver.presentation.controllers.server_list import ServerStatus

STATUS_KEYS = {
    ServerStatus.STOPPED: "status.server.stopped",
    ServerStatus.STARTING: "status.server.starting",
    ServerStatus.RUNNING: "status.server.running",
    ServerStatus.STOPPING: "status.server.stopping",
    ServerStatus.UNKNOWN: "status.server.unknown",
}
