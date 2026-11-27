"""Versioned JSON file for application settings: ``<servers root>/mcserver_settings.json``.

The legacy application keeps its own ``app_settings.json`` in the same folder;
that file is never read or written here. A damaged file never stops the
application: defaults are used, and the damaged file is kept beside the new one
(``.corrupt-<timestamp>``) when settings are saved next.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from mcserver.application.settings import ApplicationSettings, InvalidSettings
from mcserver.infrastructure.server_configuration_store import ServerConfigurationWriteFailed

SETTINGS_FILE_NAME = "mcserver_settings.json"
FORMAT_VERSION = 1
_FIELDS = (
    "language",
    "java_executable",
    "stop_timeout_seconds",
    "startup_timeout_seconds",
    "legacy_import_offered",
    "auto_restart",
    "first_run_completed",
    "theme",
)


class JsonApplicationSettingsStore:
    """Implement ``ApplicationSettingsRepository`` with one atomically written JSON file."""

    def __init__(self, servers_directory: Path) -> None:
        """Keep the file in ``servers_directory``."""
        self._directory = servers_directory.resolve()
        self._path = self._directory / SETTINGS_FILE_NAME
        self._load_problem: str | None = None

    @property
    def path(self) -> Path:
        """Return the settings file location."""
        return self._path

    @property
    def load_problem(self) -> str | None:
        """Describe why the last ``load`` used defaults, if it did."""
        return self._load_problem

    def load(self) -> ApplicationSettings:
        """Return stored settings; a missing file gives defaults, a damaged one defaults plus ``load_problem``."""
        self._load_problem = None
        try:
            text = self._path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            return ApplicationSettings()
        except (OSError, UnicodeDecodeError) as error:
            return self._defaults(f"could not read {self._path.name}: {error}")
        try:
            return self._parse(json.loads(text))
        except (ValueError, InvalidSettings) as error:
            return self._defaults(f"{self._path.name} is invalid: {error}")

    def save(self, settings: ApplicationSettings) -> None:
        """Write ``settings`` through a temporary file and an atomic replace."""
        payload = {"format_version": FORMAT_VERSION, "settings": {name: getattr(settings, name) for name in _FIELDS}}
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        temporary: Path | None = None
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            if self._load_problem is not None and self._path.exists():
                os.replace(self._path, self._path.with_name(f"{SETTINGS_FILE_NAME}.corrupt-{int(time.time())}"))
                self._load_problem = None
            descriptor, name = tempfile.mkstemp(prefix=f".{SETTINGS_FILE_NAME}.", suffix=".tmp", dir=self._directory)
            temporary = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
                file.write(text)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self._path)
        except OSError as error:
            raise ServerConfigurationWriteFailed(f"Could not write {self._path}.") from error
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)

    def _defaults(self, problem: str) -> ApplicationSettings:
        self._load_problem = problem
        return ApplicationSettings()

    @staticmethod
    def _parse(data: Any) -> ApplicationSettings:
        if not isinstance(data, dict) or data.get("format_version") != FORMAT_VERSION:
            raise ValueError("unsupported or missing format_version")
        values = data.get("settings")
        if not isinstance(values, dict):
            raise ValueError("'settings' must be an object")
        # Unknown keys are ignored so a newer MCServer's extra settings do not reset these.
        return ApplicationSettings(**{name: values[name] for name in _FIELDS if name in values})
