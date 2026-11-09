"""Discovery and validation of a Java runtime for Minecraft server processes."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from subprocess import DEVNULL, PIPE, TimeoutExpired, run  # nosec B404


class JavaRuntimeSource(str, Enum):
    """The source from which a usable Java runtime was resolved."""

    BUNDLED = "bundled"
    SYSTEM = "system"


class JavaRuntimeNotFound(RuntimeError):
    """Raised when no usable Java runtime can be resolved."""


@dataclass(frozen=True, slots=True)
class JavaRuntime:
    """A validated Java executable and the source that supplied it."""

    executable: Path
    source: JavaRuntimeSource


class JavaRuntimeResolver:
    """Resolve a validated bundled runtime before falling back to system Java."""

    def __init__(self, bundled_executables: tuple[Path, ...] = ()) -> None:
        """Configure optional bundled Java candidates to try before system Java."""
        self._bundled_executables = bundled_executables

    @classmethod
    def for_current_application(cls) -> JavaRuntimeResolver:
        """Create a resolver for the conventional JRE location beside this application."""
        executable_name = "java.exe" if sys.platform == "win32" else "java"
        bundled_java = Path(sys.executable).parent / "jre" / "bin" / executable_name
        return cls((bundled_java,))

    def resolve(self) -> JavaRuntime:
        """Return the first valid bundled runtime, otherwise a valid system Java runtime."""
        for executable in self._bundled_executables:
            if self._is_usable(executable):
                return JavaRuntime(executable.resolve(), JavaRuntimeSource.BUNDLED)

        system_java = shutil.which("java")
        if system_java is not None and self._is_usable(Path(system_java)):
            return JavaRuntime(Path(system_java).resolve(), JavaRuntimeSource.SYSTEM)
        raise JavaRuntimeNotFound("No usable Java runtime was found.")

    @staticmethod
    def _is_usable(executable: Path) -> bool:
        """Check that a candidate exists and accepts Java's version command."""
        if not executable.is_file():
            return False
        try:
            result = run(  # nosec B603
                [str(executable), "-version"],
                stdin=DEVNULL,
                stdout=PIPE,
                stderr=PIPE,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, TimeoutExpired):
            return False
        return result.returncode == 0
