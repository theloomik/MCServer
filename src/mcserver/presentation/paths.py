"""Location of the managed servers folder, shared with the legacy application."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path


def servers_root(
    *,
    frozen: bool | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    cwd: Path | None = None,
) -> Path:
    """Return the servers folder exactly as legacy ``ServerManager`` chooses it.

    A packaged application (PyInstaller sets ``sys.frozen``) keeps user data in
    ``%LOCALAPPDATA%\\MCServer\\servers``; a development run uses
    ``minecraft_servers`` in the current working directory. Sharing the folder
    lets the new GUI see the same servers and the legacy file for import.
    Nothing is created here; parameters exist for tests.
    """
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        variables = os.environ if environ is None else environ
        home_directory = Path.home() if home is None else home
        local_app_data = Path(variables.get("LOCALAPPDATA", str(home_directory / "AppData" / "Local")))
        return (local_app_data / "MCServer" / "servers").resolve()
    working_directory = Path.cwd() if cwd is None else cwd
    return (working_directory / "minecraft_servers").resolve()
