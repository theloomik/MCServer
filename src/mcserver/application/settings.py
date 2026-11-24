"""Application settings use case: what the user chose, validated, stored and applied (M2-BE-06)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Protocol

from mcserver.application.errors import InvalidJavaExecutable
from mcserver.application.ports import JavaRuntimeProvider

_logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("en", "uk")
STOP_TIMEOUT_RANGE = (10, 3600)
STARTUP_TIMEOUT_RANGE = (30, 7200)


class InvalidSettings(ValueError):
    """Raised when a settings value is outside its allowed range."""


@dataclass(frozen=True, slots=True)
class ApplicationSettings:
    """Settings that apply to the whole application.

    ``language`` ``None`` follows the Windows UI language (Ukrainian or
    English, otherwise Ukrainian). ``java_executable`` ``None`` detects Java
    automatically. ``legacy_import_offered`` remembers that the one-time
    offer to import MCServer 0.9.1 servers was shown.
    """

    language: str | None = None
    java_executable: str | None = None
    stop_timeout_seconds: int = 90
    startup_timeout_seconds: int = 600
    legacy_import_offered: bool = False
    auto_restart: bool = False
    """Start a crashed server again (at most 3 times in 10 minutes, M3-BE-05)."""
    first_run_completed: bool = False
    """The first-run guide was finished or skipped (M4-GUI-08); it can be opened again from the File menu."""

    def __post_init__(self) -> None:
        """Reject values the application cannot use."""
        if self.language is not None and self.language not in SUPPORTED_LANGUAGES:
            raise InvalidSettings(f"Unsupported language: {self.language!r}.")
        if self.java_executable is not None and (
            not isinstance(self.java_executable, str) or not self.java_executable.strip()
        ):
            raise InvalidSettings("The Java executable must be a non-empty path.")
        for name, value, (low, high) in (
            ("stop timeout", self.stop_timeout_seconds, STOP_TIMEOUT_RANGE),
            ("startup timeout", self.startup_timeout_seconds, STARTUP_TIMEOUT_RANGE),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise InvalidSettings(f"The {name} must be between {low} and {high} seconds.")
        for flag in ("legacy_import_offered", "auto_restart", "first_run_completed"):
            if not isinstance(getattr(self, flag), bool):
                raise InvalidSettings(f"{flag} must be true or false.")


class ApplicationSettingsRepository(Protocol):
    """Load and save ``ApplicationSettings``.

    ``load`` never raises for a damaged file: it returns defaults and reports
    the problem through ``load_problem``. ``save`` raises
    ``ServerConfigurationStorageError`` subclasses on write failures.
    """

    @property
    def load_problem(self) -> str | None:
        """Describe why the last ``load`` fell back to defaults, if it did."""

    def load(self) -> ApplicationSettings:
        """Return the stored settings, or defaults when there are none or they are unreadable."""

    def save(self, settings: ApplicationSettings) -> None:
        """Store ``settings`` atomically."""


class TimeoutTarget(Protocol):
    """Something whose start and stop timeouts follow the settings (the coordinator)."""

    def configure_timeouts(self, startup_timeout: float, stop_timeout: float) -> None:
        """Use these timeouts for later starts and stops."""


class SettingsService:
    """Read, change and apply application settings."""

    def __init__(
        self,
        repository: ApplicationSettingsRepository,
        java: JavaRuntimeProvider,
        timeouts: TimeoutTarget | None = None,
    ) -> None:
        """Load the settings once; call ``apply`` to make them effective."""
        self._repository = repository
        self._java = java
        self._timeouts = timeouts
        self._settings = repository.load()
        if repository.load_problem:
            _logger.warning("Settings were reset to defaults: %s", repository.load_problem)

    @property
    def current(self) -> ApplicationSettings:
        """Return the settings in effect."""
        return self._settings

    @property
    def load_problem(self) -> str | None:
        """Return why the stored settings could not be used, if that happened."""
        return self._repository.load_problem

    def apply(self, *, include_timeouts: bool = True) -> None:
        """Make the current settings effective; a configured Java that no longer runs is ignored (and logged)."""
        try:
            self._java.configure(self._settings.java_executable)
        except InvalidJavaExecutable:
            _logger.warning(
                "The configured Java %r does not run; detecting Java instead.", self._settings.java_executable
            )
            self._java.configure(None)
        if include_timeouts and self._timeouts is not None:
            self._timeouts.configure_timeouts(
                self._settings.startup_timeout_seconds, self._settings.stop_timeout_seconds
            )

    def update(self, **changes: object) -> ApplicationSettings:
        """Validate, store and apply changed settings; raise ``InvalidSettings`` or ``InvalidJavaExecutable``."""
        updated = replace(self._settings, **changes)  # type: ignore[arg-type]
        if updated.java_executable != self._settings.java_executable:
            self._java.configure(updated.java_executable)  # validates before anything is saved
        self._repository.save(updated)
        self._settings = updated
        if self._timeouts is not None:
            self._timeouts.configure_timeouts(updated.startup_timeout_seconds, updated.stop_timeout_seconds)
        return updated
