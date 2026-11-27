"""Use case for showing and choosing the Java runtime used to start servers."""

from __future__ import annotations

from dataclasses import dataclass

from mcserver.application.errors import JavaNotFound
from mcserver.application.ports import JavaInstallation, JavaRuntimeProvider


@dataclass(frozen=True, slots=True)
class JavaStatus:
    """What the application knows about Java right now."""

    installation: JavaInstallation | None
    configured_executable: str | None

    @property
    def available(self) -> bool:
        """Return whether a usable Java was found."""
        return self.installation is not None


class JavaSetup:
    """Detect Java on demand and let the user choose an executable (no JRE is bundled).

    The choice lasts for this session; persisting it is part of the application
    settings (M2-BE-06).
    """

    def __init__(self, provider: JavaRuntimeProvider) -> None:
        """Use ``provider`` for every lookup."""
        self._provider = provider

    def status(self) -> JavaStatus:
        """Detect Java now (it may have been installed since the last check)."""
        try:
            installation: JavaInstallation | None = self._provider.find()
        except JavaNotFound:
            installation = None
        return JavaStatus(installation, self._provider.configured_executable)

    def check(self, executable: str) -> JavaInstallation:
        """Check ``executable`` without using it yet; raise ``InvalidJavaExecutable`` if it does not run."""
        return self._provider.inspect(executable)

    def choose_executable(self, executable: str | None) -> JavaStatus:
        """Use ``executable`` for later starts (``None`` = detect automatically); raise ``InvalidJavaExecutable``."""
        self._provider.configure(executable)
        return self.status()
