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
    "server_list.title": "All servers",
    "server_list.refresh": "Refresh",
    "server_list.item": "{server_id}\n{status}",
    "server_list.subtitle": "{status} · {memory}",
    "server_list.empty": "No servers yet.\nServers you create will appear here.",
    "server_list.error.load": (
        "The server list couldn't be loaded. The configuration file may be damaged or from a newer "
        "MCServer version. Details were written to the log."
    ),
    "server_details.error.gone": "This server no longer exists. Refresh the list to see the current servers.",
    "server_details.error.load": "This server's details couldn't be loaded. Details were written to the log.",
    "server_details.field.directory": "Folder",
    "server_details.field.location": "Location",
    "server_details.field.jar_file": "Server JAR",
    "server_details.field.memory": "Memory",
    "server_details.memory_value": "{memory_mb} MB",
    "server_details.next_launch_note": "Configuration changes take effect the next time the server starts.",
    "welcome.title": "Welcome to MCServer",
    "welcome.text": "Select a server in the list on the left.",
    "dashboard.subtitle": "{jar_file} · {memory}",
    "dashboard.start": "Start",
    "dashboard.starting": "Starting…",
    "dashboard.stop": "Stop",
    "dashboard.stopping": "Stopping…",
    "dashboard.hint.java_missing": "Java was not found, so servers can't be started. Install Java and restart MCServer.",
    "dashboard.hint.other_running": "Stop {server_id} first: MCServer runs one server at a time.",
    "dashboard.hint.running": "Stopping sends the stop command and waits for the server to save.",
    "dashboard.notice.stopped_unexpectedly": "{server_id} stopped unexpectedly. Check the console for details.",
    "dashboard.info.title": "Server",
    "dashboard.open_folder": "Open folder",
    "dashboard.open_folder_failed": "Couldn't open {path}. The folder may not exist yet.",
    "console.title": "Terminal >_",
    "console.clear": "Clear",
    "console.placeholder": "Server output will appear here.",
    "console.unavailable": "The console is unavailable because Java was not found.",
    "errors.another_server_running": "{server_id} is already running. Stop it before starting another server.",
    "errors.start_failed": "{server_id} couldn't be started. Hover here for technical details.",
    "errors.stop_failed": (
        "MCServer couldn't confirm that {server_id} stopped. It may still be running; check Task Manager for "
        "java.exe before starting it again. Hover here for technical details."
    ),
    "errors.unexpected": "Something went wrong. Hover here for technical details.",
    "exit.confirm.title": "Stop the server?",
    "exit.confirm.text": "{server_id} is still running. Stop it and exit MCServer?",
    "exit.stopping": "Stopping {server_id} before exiting…",
    "exit.wait_for_operation": "Please wait until the current operation finishes.",
}
