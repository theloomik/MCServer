"""Persistent configuration of one managed Minecraft server."""

from dataclasses import dataclass

from mcserver.domain.errors import InvalidServerConfiguration

MIN_MEMORY_MB = 512
MAX_MEMORY_MB = 262144

_FORBIDDEN_NAME_CHARACTERS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)


def is_safe_name(name: object) -> bool:
    """Return whether ``name`` is usable as a single, portable file-system name segment.

    The rule matches the legacy application's server-name policy and also
    rejects Windows reserved device names.
    """
    if not isinstance(name, str) or not name or name in {".", ".."}:
        return False
    if name != name.strip() or name.endswith("."):
        return False
    if any(ord(character) < 32 or character in _FORBIDDEN_NAME_CHARACTERS for character in name):
        return False
    return name.split(".")[0].upper() not in _WINDOWS_RESERVED_NAMES


@dataclass(frozen=True, slots=True)
class ServerConfiguration:
    """What MCServer must remember to launch a server; no runtime state.

    ``directory`` is the server folder name relative to the managed servers
    root and ``jar_file`` the JAR name inside that folder. Absolute paths,
    JVM arguments and the Java executable are derived when launching.
    """

    server_id: str
    directory: str
    jar_file: str
    memory_mb: int

    def __post_init__(self) -> None:
        """Reject configurations that could not be launched safely."""
        if not is_safe_name(self.server_id):
            raise InvalidServerConfiguration(f"Invalid server identifier: {self.server_id!r}.")
        if not is_safe_name(self.directory):
            raise InvalidServerConfiguration(f"Invalid server directory name: {self.directory!r}.")
        if not is_safe_name(self.jar_file) or not self.jar_file.lower().endswith(".jar"):
            raise InvalidServerConfiguration(f"Invalid server JAR file name: {self.jar_file!r}.")
        if isinstance(self.memory_mb, bool) or not isinstance(self.memory_mb, int):
            raise InvalidServerConfiguration("Server memory must be an integer number of megabytes.")
        if not MIN_MEMORY_MB <= self.memory_mb <= MAX_MEMORY_MB:
            raise InvalidServerConfiguration(
                f"Server memory must be between {MIN_MEMORY_MB} and {MAX_MEMORY_MB} MB, got {self.memory_mb}."
            )
