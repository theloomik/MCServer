"""MCServer's own log file, for bug reports (release polish).

The packaged app has no console, so without a file the warnings and errors MCServer
logs would be lost. They go to ``mcserver.log`` in the logs folder
(``%LOCALAPPDATA%\\MCServer\\logs`` for the installed app), rotated at 1 MB with three
older files kept, so it never grows without limit. The log stays on this PC.
"""

from __future__ import annotations

import logging
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE_NAME = "mcserver.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 3
_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def logs_folder(servers_root: Path) -> Path:
    """Return the logs folder: next to the servers folder (``%LOCALAPPDATA%\\MCServer\\logs`` when installed)."""
    return servers_root.parent / "logs"


def start_log_file(folder: Path, version: str) -> Path | None:
    """Log INFO and above to ``folder/mcserver.log``; return the file, or ``None`` if it cannot be written.

    Calling it again for the same file does nothing. A folder that cannot be created
    (read-only, no permission) leaves MCServer running without a log file.
    """
    path = folder / LOG_FILE_NAME
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == path.resolve():
            return path
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
    except OSError:
        return None
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.setLevel(logging.INFO)
    root.addHandler(handler)
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    logging.getLogger("mcserver").info(
        "MCServer %s starting (Python %s, %s, %s).",
        version,
        platform.python_version(),
        platform.platform(),
        "installed" if getattr(sys, "frozen", False) else "from source",
    )
    return path


__all__ = ["BACKUP_COUNT", "LOG_FILE_NAME", "MAX_BYTES", "logs_folder", "start_log_file"]
