"""English message catalog (the reference language; every key must exist here)."""

from mcserver.presentation.i18n.catalog import Catalog

MESSAGES: Catalog = {
    "app.title": "MCServer",
    "menu.file": "&File",
    "menu.file.refresh": "&Refresh servers",
    "menu.file.exit": "E&xit",
    "status.servers_folder": "Servers folder: {path}",
    "status.java_available": "Java: ready",
    "status.java_missing": "Java not found: servers can be viewed but not started.",
    "status.server.stopped": "Stopped",
    "status.server.starting": "Starting",
    "status.server.running": "Running",
    "status.server.stopping": "Stopping",
    "status.server.unknown": "Status unavailable",
    "status.server.unknown_hint": "MCServer can't run or track servers until Java is installed.",
    "server_list.title": "Servers",
    "server_list.refresh": "Refresh",
    "server_list.item": "{server_id}\n{status}",
    "server_list.empty": "No servers yet.\nServers you create will appear here.",
    "server_list.error.load": (
        "The server list couldn't be loaded. The configuration file may be damaged or from a newer "
        "MCServer version. Details were written to the log."
    ),
    "server_details.empty": "Select a server to see its details.",
    "server_details.error.gone": "This server no longer exists. Refresh the list to see the current servers.",
    "server_details.error.load": "This server's details couldn't be loaded. Details were written to the log.",
    "server_details.field.server_id": "Server ID",
    "server_details.field.directory": "Folder",
    "server_details.field.location": "Location",
    "server_details.field.jar_file": "Server JAR",
    "server_details.field.memory": "Memory",
    "server_details.field.status": "Status",
    "server_details.memory_value": "{memory_mb} MB",
    "server_details.next_launch_note": "Configuration changes take effect the next time the server starts.",
}
