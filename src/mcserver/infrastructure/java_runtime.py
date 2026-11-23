"""Discovery and validation of Java runtimes for Minecraft server processes.

No JRE is bundled with MCServer 2.0. Java is looked up on every request, so a
runtime installed while the application runs is found without a restart.
Search order: the executable the user configured, a ``jre`` folder next to the
application (a harmless legacy fallback), ``JAVA_HOME``, ``PATH``, then common
Windows installation folders.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from subprocess import DEVNULL, PIPE, TimeoutExpired, run  # nosec B404
from threading import Lock

from mcserver.application.errors import InvalidJavaExecutable, JavaNotFound
from mcserver.application.ports import JavaInstallation

_EXECUTABLE = "java.exe" if sys.platform == "win32" else "java"
_VERSION_LINE = re.compile(r'version "(?P<version>[^"]+)"')
_INSTALL_ROOTS = (
    "Java",
    "Eclipse Adoptium",
    "Eclipse Foundation",
    "Microsoft",
    "Zulu",
    "Amazon Corretto",
    "BellSoft",
    "Semeru",
    "AdoptOpenJDK",
)


class JavaRuntimeSource(str, Enum):
    """The source from which a usable Java runtime was resolved."""

    CONFIGURED = "configured"
    BUNDLED = "bundled"
    JAVA_HOME = "java_home"
    SYSTEM = "path"
    INSTALLED = "installed"


# Kept for callers that catch the infrastructure error; the application error is the contract.
JavaRuntimeNotFound = JavaNotFound


@dataclass(frozen=True, slots=True)
class JavaRuntime:
    """A validated Java executable, its major version and the source that supplied it."""

    executable: Path
    source: JavaRuntimeSource
    major_version: int = 0


def parse_java_major(version_output: str) -> int | None:
    """Return the major version from ``java -version`` output (``1.8.0_401`` → 8, ``21.0.2`` → 21, ``25`` → 25)."""
    match = _VERSION_LINE.search(version_output)
    if match is None:
        return None
    version = match.group("version")
    parts = re.split(r"[._+-]", version)
    try:
        first = int(parts[0])
        if first == 1 and len(parts) > 1:
            return int(parts[1])
        return first
    except ValueError:
        return None


VersionProbe = Callable[[Path], int | None]


def probe_java_version(executable: Path) -> int | None:
    """Run ``executable -version`` and return its major version, or ``None`` if it does not work."""
    if not executable.is_file():
        return None
    try:
        result = run(  # nosec B603
            [str(executable), "-version"],
            stdin=DEVNULL,
            stdout=PIPE,
            stderr=PIPE,
            text=True,
            timeout=10,
            check=False,
            errors="replace",
        )
    except (OSError, TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return parse_java_major(result.stderr + "\n" + result.stdout)


class JavaRuntimeResolver:
    """Implement ``JavaRuntimeProvider``: find and validate Java on every call (thread-safe)."""

    def __init__(
        self,
        bundled_executables: tuple[Path, ...] = (),
        *,
        probe: VersionProbe = probe_java_version,
        environ: Mapping[str, str] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        install_roots: Iterable[Path] | None = None,
    ) -> None:
        """Configure the search; every parameter exists so tests need no real Java."""
        self._bundled_executables = bundled_executables
        self._probe = probe
        self._environ = os.environ if environ is None else environ
        self._which = which
        self._install_roots = tuple(install_roots) if install_roots is not None else None
        self._configured: Path | None = None
        self._lock = Lock()

    @classmethod
    def for_current_application(cls) -> JavaRuntimeResolver:
        """Create a resolver that also checks a ``jre`` folder beside this application."""
        bundled_java = Path(sys.executable).parent / "jre" / "bin" / _EXECUTABLE
        return cls((bundled_java,))

    @property
    def configured_executable(self) -> str | None:
        """Return the executable chosen by the user, if any."""
        with self._lock:
            return str(self._configured) if self._configured is not None else None

    def configure(self, executable: str | None) -> JavaInstallation | None:
        """Use ``executable`` for every later lookup; ``None`` returns to automatic detection."""
        if executable is None:
            with self._lock:
                self._configured = None
            return None
        path = Path(executable)
        major = self._probe(path)
        if major is None:
            raise InvalidJavaExecutable(executable)
        with self._lock:
            self._configured = path
        return JavaInstallation(str(path.resolve()), major, JavaRuntimeSource.CONFIGURED.value)

    def inspect(self, executable: str) -> JavaInstallation:
        """Probe ``executable`` (a per-server Java) without changing the configured one."""
        path = Path(executable)
        major = self._probe(path)
        if major is None:
            raise InvalidJavaExecutable(executable)
        return JavaInstallation(str(path.resolve()), major, "server")

    def find(self, minimum_major: int | None = None) -> JavaInstallation:
        """Return the configured Java, else the first runtime meeting ``minimum_major`` (else the first found)."""
        runtime = self.resolve(minimum_major)
        return JavaInstallation(str(runtime.executable), runtime.major_version, runtime.source.value)

    def resolve(self, minimum_major: int | None = None) -> JavaRuntime:
        """Like ``find`` but returns the infrastructure ``JavaRuntime``; raises ``JavaNotFound``."""
        with self._lock:
            configured = self._configured
        if configured is not None:
            major = self._probe(configured)
            if major is None:
                raise JavaNotFound(minimum_major)
            return JavaRuntime(configured.resolve(), JavaRuntimeSource.CONFIGURED, major)

        first: JavaRuntime | None = None
        for candidate, source in self._candidates():
            major = self._probe(candidate)
            if major is None:
                continue
            runtime = JavaRuntime(candidate.resolve(), source, major)
            if minimum_major is None or major >= minimum_major:
                return runtime
            if first is None:
                first = runtime
        if first is not None:
            return first
        raise JavaNotFound(minimum_major)

    def _candidates(self) -> Iterable[tuple[Path, JavaRuntimeSource]]:
        """Yield distinct candidate executables in search order."""
        seen: set[str] = set()

        def unique(path: Path) -> bool:
            key = os.path.normcase(str(path))
            if key in seen:
                return False
            seen.add(key)
            return True

        for executable in self._bundled_executables:
            if unique(executable):
                yield executable, JavaRuntimeSource.BUNDLED
        java_home = self._environ.get("JAVA_HOME")
        if java_home:
            path = Path(java_home) / "bin" / _EXECUTABLE
            if unique(path):
                yield path, JavaRuntimeSource.JAVA_HOME
        on_path = self._which("java")
        if on_path is not None and unique(Path(on_path)):
            yield Path(on_path), JavaRuntimeSource.SYSTEM
        for path in self._installed():
            if unique(path):
                yield path, JavaRuntimeSource.INSTALLED

    def _installed(self) -> Iterable[Path]:
        """Yield ``bin/java.exe`` of runtimes in common installation folders (``find`` picks by version)."""
        roots = self._install_roots
        if roots is None:
            bases = [self._environ.get(name) for name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
            roots = tuple(Path(base) / vendor for base in bases if base for vendor in _INSTALL_ROOTS)
        for root in roots:
            try:
                children = sorted((child for child in root.iterdir() if child.is_dir()), reverse=True)
            except OSError:
                continue
            for child in children:
                yield child / "bin" / _EXECUTABLE
