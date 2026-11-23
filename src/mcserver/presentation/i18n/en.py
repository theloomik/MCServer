"""English message catalog (the reference language; every key must exist here)."""

from mcserver.presentation.i18n.catalog import Catalog

MESSAGES: Catalog = {
    "app.title": "MCServer",
    "menu.file": "&File",
    "menu.file.new_server": "&New server…",
    "menu.file.refresh": "&Refresh servers",
    "menu.file.exit": "E&xit",
    "menu.file.import_folder": "&Import server folder…",
    "menu.file.import_legacy": "Import from MCServer &0.9.1…",
    "menu.file.settings": "&Settings…",
    "status.servers_folder": "Servers folder: {path}",
    "status.java_available": "Java: ready",
    "status.java_ready": "Java {major}: ready",
    "status.java_missing": "Java not found: servers can't be started until Java is installed or chosen.",
    "status.java_check": "Check Java",
    "status.java_choose": "Choose Java…",
    "status.server.stopped": "Stopped",
    "status.server.starting": "Starting",
    "status.server.running": "Running",
    "status.server.stopping": "Stopping",
    "status.server.killing": "Killing",
    "status.server.unknown": "Status unavailable",
    "server_list.title": "All servers",
    "server_list.refresh": "Refresh",
    "server_list.create": "+  Create server",
    "server_list.item": "{server_id}\n{status}",
    "server_list.subtitle": "{status} · {memory}",
    "server_list.empty": (
        "No servers yet.\nCreate one, or use File › Import server folder for a server you already have."
    ),
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
    "dashboard.success.created": "{server_id} was created. Press Start when you're ready.",
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
    "errors.server_id_taken": "A server with the ID {server_id} already exists. Choose another ID.",
    "errors.directory_in_use": "The folder {directory} is already used by {server_id}. Choose another folder.",
    "errors.directory_exists": (
        "A folder named {directory} already exists in the servers folder. Its files were not changed; "
        "choose another folder name."
    ),
    "errors.jar_exists": "{directory} already contains {jar_file}; it was not overwritten.",
    "errors.invalid_source_jar": "The selected file can't be used: {reason}.",
    "errors.invalid_configuration": "These settings can't be used: {reason}",
    "errors.provisioning_failed": "The server files couldn't be prepared. Nothing was kept from this attempt.",
    "errors.storage_failed": "MCServer couldn't save the server list. Nothing was created.",
    "errors.provisioning_rollback_failed": (
        "Creating {server_id} failed and some files could not be cleaned up: {leftovers}. You can delete them manually."
    ),
    "errors.creation_rollback_failed": (
        "Creating {server_id} failed and cleanup was incomplete: its configuration may still be listed. "
        "Files left on disk: {leftovers}. Check the details below and remove what is left manually."
    ),
    "create.title": "Create server",
    "create.subtitle": "Set up a new server from a server JAR you already have (Paper, Fabric, Vanilla…).",
    "create.server_id.label": "Server ID",
    "create.server_id.placeholder": "e.g. survival",
    "create.server_id.hint": "Shown in the server list. Must be unique.",
    "create.directory.label": "Folder",
    "create.directory.placeholder": "Same as the server ID",
    "create.directory.hint": "Created inside the servers folder. Defaults to the server ID.",
    "create.source_jar.label": "Server JAR",
    "create.jar.placeholder": "No file selected",
    "create.jar.browse": "Browse…",
    "create.jar.dialog_title": "Choose the server JAR",
    "create.jar.dialog_filter": "Java archives (*.jar)",
    "create.source_jar.hint": "Copied into the server folder; the original file is not changed.",
    "create.memory_mb.label": "Memory",
    "create.memory_mb.hint": "How much RAM the server may use.",
    "create.memory.suffix": " MB",
    "create.cancel": "Cancel",
    "create.submit": "Create server",
    "create.submitting": "Creating…",
    "create.progress": "Creating the server folder and copying the JAR. This can't be cancelled once it has started.",
    "create.done": "{server_id} was created.",
    "create.error.server_id_required": "Enter a server ID.",
    "create.error.server_id_invalid": (
        'Use letters, numbers, spaces, dots or dashes; no \\ / : * ? " < > | and no leading or trailing spaces.'
    ),
    "create.error.server_id_taken": "This ID is already used by another server.",
    "create.error.directory_required": "Enter a folder name.",
    "create.error.directory_invalid": "This folder name isn't allowed. Use a simple name without \\ / : * ? \" < > |.",
    "create.error.directory_taken": "This folder is already used by {server_id}.",
    "create.error.jar_required": "Choose the server JAR file.",
    "create.error.jar_invalid": "Choose a .jar file whose name has no special characters.",
    "create.error.memory_range": "Choose between {minimum} and {maximum} MB.",
    "exit.confirm.title": "Stop the server?",
    "exit.confirm.text": "{server_id} is still running. Stop it and exit MCServer?",
    "exit.stopping": "Stopping {server_id} before exiting…",
    "exit.wait_for_operation": "Please wait until the current operation finishes.",
    "exit.stop_timed_out.title": "The server is still stopping",
    "exit.stop_timed_out.text": (
        "{server_id} didn't stop within {timeout} seconds. Keep waiting, kill it (changes since its last autosave "
        "can be lost), or cancel closing MCServer?"
    ),
    "exit.keep_waiting": "Keep waiting",
    "exit.kill": "Kill and exit",
    "exit.cancel": "Cancel",
    "session.block_reason": "MCServer is stopping your Minecraft server so that the world is saved.",
    "dashboard.kill": "Kill",
    "dashboard.killing": "Killing…",
    "dashboard.details": "Details…",
    "dashboard.hint.starting": "Waiting for the server to finish loading. It shows Running once players can join.",
    "dashboard.hint.stop_timed_out": (
        "{server_id} hasn't finished stopping. Wait with Stop, or Kill it (changes since the last autosave can be lost)."
    ),
    "dashboard.hint.stopping": "The server is saving and shutting down.",
    "dashboard.failure.start_timeout": (
        "{server_id} didn't finish starting in time, so MCServer asked it to stop (it was not killed). {hint}"
    ),
    "dashboard.failure.unexpected_exit": "{server_id} stopped unexpectedly (exit code {exit_code}). {hint}",
    "dashboard.warning.java_requirement_unknown": (
        "MCServer can't verify which Java Minecraft {version} needs, so it started with Java {java_major}. "
        "If the server fails, install a newer Java."
    ),
    "dashboard.warning.java_outdated_allowed": (
        "Started with Java {java_major} although Java {required} is required; the server will probably fail."
    ),
    "dashboard.notice.command_failed": "The command couldn't be sent: {reason}",
    "hint.eula_not_accepted": "The Minecraft EULA wasn't accepted.",
    "hint.port_in_use": "Another program is already using the server's port.",
    "hint.java_too_old": "This server needs a newer Java version.",
    "hint.out_of_memory": "The server ran out of memory or couldn't reserve it. Try less memory or close other programs.",
    "hint.corrupt_jar": "The server JAR looks damaged or unreadable. Replace it with a fresh download.",
    "hint.unknown": "See Details for the last console lines.",
    "kill.confirm.title": "Kill the server?",
    "kill.confirm.text": (
        "Killing {server_id} ends it immediately without saving. Changes since its last autosave can be lost and a "
        "chunk being written can be damaged. Kill it anyway?"
    ),
    "details.title": "Technical details",
    "details.copy": "Copy",
    "details.close": "Close",
    "details.exit_code": "Exit code: {exit_code}",
    "details.last_lines": "Last console lines:",
    "console.input.placeholder": "Type a command, e.g. say hi, and press Enter",
    "console.send": "Send",
    "errors.eula_not_accepted": "The Minecraft EULA hasn't been accepted for {server_id}.",
    "errors.server_not_running": "{server_id} isn't running, so the command wasn't sent.",
    "errors.invalid_command": "Enter a command on a single line.",
    "errors.command_failed": "The command couldn't be sent to {server_id}; it may be shutting down.",
    "errors.java_not_found": "No working Java was found, so the server can't start.",
    "errors.java_too_old": "{server_id} needs Java {required}, but Java {found} was found.",
    "errors.invalid_java": "The selected file isn't a working Java: {executable}",
    "errors.world_in_use": (
        "The world {world} of {server_id} is in use by another program, probably a server that is still running. "
        "Close it first."
    ),
    "errors.stop_timed_out": (
        "{server_id} didn't stop within {timeout} seconds and is still running. Press Stop to keep waiting, or Kill it."
    ),
    "errors.process_guard": (
        "{server_id} couldn't be started under MCServer's process protection, so it was not started at all."
    ),
    "eula.title": "Accept the Minecraft EULA?",
    "eula.text": (
        "To run {server_id}, you must accept the Minecraft End User License Agreement (EULA). "
        "Read it at https://aka.ms/MinecraftEULA. Accept it and start the server?"
    ),
    "create.eula.label": "I have read and accept the Minecraft EULA",
    "create.eula.hint": "Required to run a Minecraft server. Read it at https://aka.ms/MinecraftEULA.",
    "create.error.eula_required": "Accept the Minecraft EULA to create the server.",
    "java.dialog.title": "Java is needed",
    "java.missing.text": (
        "No working Java was found.{needed} Install a Java runtime, for example Eclipse Temurin "
        "(https://adoptium.net), then press Check again, or choose java.exe yourself."
    ),
    "java.needed": " This server needs Java {required} or newer.",
    "java.too_old.text": (
        "{server_id} needs Java {required}, but MCServer found Java {found} ({executable}). Install a newer Java "
        "(for example from https://adoptium.net), choose another java.exe, or start anyway (the server will "
        "probably fail)."
    ),
    "java.found": "Found Java {major}: {executable}",
    "java.check": "Check again",
    "java.choose": "Choose java.exe…",
    "java.start_anyway": "Start anyway",
    "java.cancel": "Cancel",
    "java.choose.dialog_title": "Choose java.exe",
    "java.choose.filter": "Java (java.exe java);;All files (*)",
    "unclean.title": "{server_id} was not stopped cleanly",
    "unclean.text": (
        "When MCServer last ended, {server_id} (started {started_at}) was still running, so it was terminated "
        "without saving. Changes since its last autosave (normally within about 5 minutes) may be lost, and a "
        "chunk being written may be damaged. Start the server and check the world before playing."
    ),
    "dashboard.edit": "Edit…",
    "dashboard.delete": "Delete…",
    "legacy.offer.title": "Import your MCServer 0.9.1 servers?",
    "legacy.offer.text": {
        "one": (
            "MCServer found {count} server from MCServer 0.9.1 that is not in this list yet. Import it? "
            "Its folder is not moved or changed."
        ),
        "other": (
            "MCServer found {count} servers from MCServer 0.9.1 that are not in this list yet. Import them? "
            "Their folders are not moved or changed."
        ),
    },
    "legacy.result.title": "Import finished",
    "legacy.result.text": "Imported: {imported}. Already in the list: {skipped}. Could not be imported: {rejected}.",
    "legacy.result.rejected": "{server_id}: {reason}",
    "legacy.result.nothing": "There is nothing to import from MCServer 0.9.1.",
    "edit.title": "Edit {server_id}",
    "edit.display_name.label": "Name",
    "edit.display_name.hint": "Shown in the server list. The server ID {server_id} never changes.",
    "edit.memory.label": "Memory",
    "edit.jar.label": "Server JAR",
    "edit.jar.hint_running": "Stop the server to choose another JAR.",
    "edit.jvm.label": "Extra Java arguments",
    "edit.jvm.hint": "Separated by spaces, for example -XX:+UseG1GC. Memory is set above.",
    "edit.java.label": "Java for this server",
    "edit.java.auto": "Same as the application (automatic)",
    "edit.java.choose": "Choose…",
    "edit.java.clear": "Use automatic",
    "edit.note": "Changes apply the next time the server starts.",
    "edit.save": "Save",
    "edit.cancel": "Cancel",
    "edit.saved": "{name} was saved.",
    "delete.title": "Delete {name}?",
    "delete.text": "{name} will be removed from MCServer.",
    "delete.files": "Also move its folder to the Recycle Bin",
    "delete.files_hint": "Without this, the folder {path} stays where it is and can be imported again later.",
    "delete.confirm": "Delete",
    "delete.cancel": "Cancel",
    "delete.done.kept": "{name} was removed. Its folder was kept.",
    "delete.done.recycle_bin": "{name} was removed and its folder was moved to the Recycle Bin.",
    "delete.done.trash": "{name} was removed and its folder was moved to {location}.",
    "delete.done.missing": "{name} was removed; its folder no longer existed.",
    "adopt.title": "Import a server folder",
    "adopt.subtitle": "Use a server you already have. Its files are never moved or changed.",
    "adopt.folder.label": "Folder",
    "adopt.folder.placeholder": "No folder selected",
    "adopt.folder.browse": "Browse…",
    "adopt.folder.dialog_title": "Choose the server folder",
    "adopt.inside": "This folder is inside the servers folder, so it is used where it is.",
    "adopt.outside": "This folder will be copied into the servers folder; the original stays unchanged.",
    "adopt.jar.label": "Server JAR",
    "adopt.no_jars": "This folder has no .jar file, so it can't be imported.",
    "adopt.server_id.label": "Server ID",
    "adopt.memory.label": "Memory",
    "adopt.submit": "Import",
    "adopt.submitting": "Importing…",
    "adopt.cancel": "Cancel",
    "adopt.done": "{server_id} was imported.",
    "settings.title": "Settings",
    "settings.servers_folder": "Servers folder",
    "settings.open_folder": "Open",
    "settings.java.label": "Java",
    "settings.java.auto": "Detect automatically",
    "settings.java.choose": "Choose java.exe…",
    "settings.java.found": "{executable} (Java {major})",
    "settings.java.missing": "No Java found",
    "settings.stop_timeout.label": "Stop timeout",
    "settings.stop_timeout.hint": "How long Stop waits for the server to save before Kill is offered.",
    "settings.startup_timeout.label": "Startup timeout",
    "settings.startup_timeout.hint": "How long a start may take before MCServer stops the server gracefully.",
    "settings.seconds": " s",
    "settings.import_legacy": "Import MCServer 0.9.1 servers…",
    "settings.save": "Save",
    "settings.cancel": "Cancel",
    "settings.saved": "Settings were saved.",
    "errors.server_is_running": "{server_id} is running; stop it first.",
    "errors.files_removal_failed": (
        "The folder {directory} could be moved neither to the Recycle Bin nor to the trash folder, so nothing "
        "was deleted. {reason}"
    ),
    "errors.invalid_settings": "{reason}",
    "errors.legacy_unavailable": "The MCServer 0.9.1 server list could not be read.",
    "tabs.overview": "Overview",
    "tabs.properties": "Properties",
    "tabs.backups": "Backups",
    "metrics.title": "Resources",
    "metrics.cpu": "CPU",
    "metrics.memory": "Memory",
    "metrics.uptime": "Uptime",
    "metrics.cpu_value": "{percent} %",
    "metrics.memory_value": "{used} / {allocated} MB",
    "metrics.uptime_value": "{hours}:{minutes:02d}:{seconds:02d}",
    "metrics.idle": "-",
    "properties.title": "server.properties",
    "properties.search": "Filter properties…",
    "properties.save": "Save",
    "properties.reload": "Reload",
    "properties.missing": (
        "server.properties is created when the server starts for the first time. "
        "Values you save now are used from the first start."
    ),
    "properties.saved": "server.properties was saved.",
    "properties.saved_restart": "server.properties was saved. Restart the server to apply the changes.",
    "properties.invalid": "Some values are not valid; they are marked below and nothing was saved.",
    "properties.invalid_value": "{name}: {reason}",
    "properties.other": "Other properties",
    "properties.known": "Common properties",
    "properties.default": "server default",
    "backups.title": "Backups",
    "backups.note.placeholder": "Note for the new backup (optional)",
    "backups.create": "Back up now",
    "backups.restore": "Restore…",
    "backups.delete": "Delete…",
    "backups.empty": "No backups yet. A backup copies the world and settings; logs and caches are left out.",
    "backups.column.date": "Created",
    "backups.column.kind": "Kind",
    "backups.column.size": "Size",
    "backups.column.note": "Note",
    "backups.kind.manual": "Manual",
    "backups.kind.safety": "Before restore",
    "backups.kind.scheduled": "Scheduled",
    "backups.schedule.enabled": "Back up automatically while the server runs",
    "backups.schedule.every": "every",
    "backups.schedule.hours_suffix": " h",
    "backups.schedule.keep": "keep last",
    "backups.schedule.hint": (
        "Only scheduled backups are counted; older ones go to the Recycle Bin. Manual and "
        "before-restore backups are never removed automatically."
    ),
    "backups.schedule.saved": "Automatic backups are on for this server.",
    "backups.schedule.off": "Automatic backups are off for this server.",
    "backups.scheduled_created": (
        "Scheduled backup {backup_id} of {server_id} was created; {removed} older scheduled backup(s) "
        "moved to the Recycle Bin."
    ),
    "backups.kind.online": "{kind} (while running)",
    "backups.size_value": "{megabytes} MB",
    "backups.size_kb": "{kilobytes} KB",
    "backups.working": "Working… This can take a while for large worlds.",
    "backups.created": "Backup {backup_id} was created.",
    "backups.restored": "Backup {backup_id} was restored. The previous state was saved as {safety_id}.",
    "backups.deleted": "Backup {backup_id} was moved to the Recycle Bin.",
    "backups.deleted_trash": "Backup {backup_id} was moved to {location}.",
    "backups.restore_running": "Stop the server to restore a backup.",
    "backups.restore.title": "Restore {backup_id}?",
    "backups.restore.text": (
        "The world and settings of {name} will be replaced with this backup. MCServer first saves the current "
        "state as a new backup, and the replaced files go to the Recycle Bin. Continue?"
    ),
    "backups.restore.confirm_title": "Really restore?",
    "backups.restore.confirm_text": "{name} will be set back to {created_at}. Restore now?",
    "backups.delete.title": "Delete {backup_id}?",
    "backups.delete.text": "The backup file will be moved to the Recycle Bin.",
    "errors.server_port_in_use": (
        "Port {port} is already used by another program, probably another Minecraft server. Stop it or "
        "change server-port in Properties."
    ),
    "errors.invalid_properties": "Some server.properties values are not valid.",
    "errors.backup_not_possible": "{server_id} is starting or stopping. Try again when it is running or stopped.",
    "errors.backup_failed": "The backup operation for {server_id} failed: {reason}",
    "errors.backup_not_found": "That backup no longer exists.",
    "unclean.open_backups": "Open backups",
    "create.jar.download": "Download…",
    "catalog.title": "Download a server",
    "catalog.subtitle": (
        "Official files only: Paper from PaperMC, Vanilla from Mojang. Each file is checked against its "
        "published checksum before it is used."
    ),
    "catalog.type.label": "Server type",
    "catalog.type.hint": "Paper runs plugins and is faster; Vanilla is the unmodified game.",
    "catalog.type.paper": "Paper",
    "catalog.type.vanilla": "Vanilla",
    "catalog.unstable": "Show test versions",
    "catalog.version.label": "Minecraft version",
    "catalog.version.unstable": "{version} (test version)",
    "catalog.loading": "Loading versions…",
    "catalog.resolving": "Checking the download…",
    "catalog.details": "{file_name}, about {size} MB.",
    "catalog.java": "Needs Java {java} or newer.",
    "catalog.java_unknown": "The required Java version is not published for this version.",
    "catalog.experimental_build": "The newest Paper build of this version is experimental.",
    "catalog.cancelling": "Cancelling…",
    "catalog.download": "Download",
    "catalog.downloading": "Downloading…",
    "catalog.cancel": "Cancel",
    "catalog.stop": "Stop download",
    "errors.catalog_unavailable": "The server list could not be loaded: {reason}. Check the internet connection.",
    "errors.download_failed": "{file_name} could not be downloaded: {reason}. Nothing was kept.",
    "tabs.worlds": "Worlds",
    "worlds.title": "Worlds",
    "worlds.new": "New world…",
    "worlds.import_folder": "Import folder…",
    "worlds.import_zip": "Import ZIP…",
    "worlds.use": "Use this world",
    "worlds.export": "Export ZIP…",
    "worlds.delete": "Delete…",
    "worlds.column.name": "World",
    "worlds.column.size": "Size",
    "worlds.column.modified": "Last played",
    "worlds.column.dimensions": "Folders",
    "worlds.active_name": "{name} (current)",
    "worlds.folders": "{folders}",
    "worlds.current": "The server loads {name}. Switching takes effect on the next start.",
    "worlds.current_new": "The server generates a new world {name} on its next start.",
    "worlds.empty": "No worlds yet. The server creates its world on the first start.",
    "worlds.stop_to_switch": "Stop the server to switch or create worlds.",
    "worlds.working": "Working… Large worlds take a while.",
    "worlds.used": "{name} is now the current world. It is loaded on the next start.",
    "worlds.created": "The new world {name} is generated on the next start.",
    "worlds.imported": '{name} was imported. Choose "Use this world" to play it.',
    "worlds.exported": "{name} was saved to {path}.",
    "worlds.deleted": "{name} was moved to the Recycle Bin.",
    "worlds.deleted_trash": "{name} was moved to {location}.",
    "worlds.new.title": "New world",
    "worlds.new.name": "Name of the new world:",
    "worlds.new.seed": "Seed (leave empty for a random world):",
    "worlds.import.title": "Import world",
    "worlds.import.name": "Name for the imported world:",
    "worlds.import_folder.title": "Choose a world folder (with level.dat)",
    "worlds.import_zip.title": "Choose a world ZIP file",
    "worlds.export.title": "Export world",
    "worlds.zip_filter": "ZIP archives (*.zip)",
    "worlds.delete.title": "Delete {name}?",
    "worlds.delete.text": "The world {name} and its Nether and End folders will be moved to the Recycle Bin.",
    "errors.world_not_found": "The world {name} no longer exists.",
    "errors.world_exists": "This server already has a folder named {name}. Choose another name.",
    "errors.world_is_active": (
        "{name} is the current world. Switch to another world first, or make a backup to copy it while the server runs."
    ),
    "errors.invalid_world_name": (
        "{name} cannot be used as a world name. Use letters, digits, - and _, and do not end it with "
        "_nether or _the_end."
    ),
    "errors.invalid_world_source": "This world cannot be imported: {reason}.",
    "metrics.players": "Players",
    "metrics.players_value": "{count} / {maximum}",
    "metrics.tps": "TPS",
    "metrics.tps_value": "{tps}",
    "metrics.players_names": "{names}",
    "dashboard.restart": "Restart",
    "dashboard.restarting": "Restarting…",
    "dashboard.hint.auto_restarting": (
        "The server crashed. It starts again automatically in {delay} s (attempt {attempt} of {limit})."
    ),
    "dashboard.hint.auto_restart_gave_up": (
        "The server crashed {limit} times within 10 minutes, so it was not started again. "
        "Check the details before starting it."
    ),
    "dashboard.notice.auto_restarted": "Started again automatically after a crash (attempt {attempt} of {limit}).",
    "dashboard.open_logs": "Open logs",
    "dashboard.no_logs": "This server has no logs folder yet; it is created on the first start.",
    "dashboard.address": "LAN address",
    "dashboard.address_unknown": "Not connected to a network",
    "dashboard.copy_address": "Copy",
    "dashboard.address_copied": "Copied {address}.",
    "console.save": "Save…",
    "console.save_title": "Save console log",
    "console.save_filter": "Log files (*.log *.txt)",
    "console.saved": "Console log saved to {path}.",
    "console.save_failed": "The console log could not be saved to {path}.",
    "console.filter.all": "All lines",
    "console.filter.warnings": "Warnings and errors",
    "settings.auto_restart.label": "Restart a server automatically after a crash",
    "settings.auto_restart.hint": (
        "At most 3 times within 10 minutes. A server you stop or kill, or one that does not finish "
        "starting, is never restarted."
    ),
}
