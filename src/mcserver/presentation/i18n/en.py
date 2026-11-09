"""English message catalog (the reference language; every key must exist here)."""

from mcserver.presentation.i18n.catalog import Catalog

MESSAGES: Catalog = {
    "app.title": "MCServer",
    "menu.file": "&File",
    "menu.file.exit": "E&xit",
    "main.placeholder": "Your servers will appear here.",
    "status.servers_folder": "Servers folder: {path}",
    "status.java_available": "Java: ready",
    "status.java_missing": "Java not found: servers can be created and edited, but not started.",
}
