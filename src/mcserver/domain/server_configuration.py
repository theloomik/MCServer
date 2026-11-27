"""Persistent configuration of one managed Minecraft server."""

from dataclasses import dataclass

from mcserver.domain.errors import InvalidServerConfiguration

MIN_MEMORY_MB = 512
MAX_MEMORY_MB = 262144
MAX_DISPLAY_NAME_LENGTH = 64
MAX_JVM_ARGUMENTS = 32
MAX_JVM_ARGUMENT_LENGTH = 512
MAX_LABEL_LENGTH = 32

_FORBIDDEN_NAME_CHARACTERS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)
# MCServer sets these itself: memory comes from memory_mb and the JAR from jar_file.
_RESERVED_JVM_PREFIXES = ("-Xmx", "-Xms", "-XX:MaxRAM")
_RESERVED_JVM_ARGUMENTS = frozenset({"-jar", "-cp", "-classpath", "--class-path"})


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


def _has_control_characters(text: str) -> bool:
    return any(ord(character) < 32 for character in text)


def validate_jvm_arguments(arguments: object) -> tuple[str, ...]:
    """Return ``arguments`` as a tuple or raise ``InvalidServerConfiguration``.

    Arguments are passed to Java as separate items (never through a shell).
    Memory and class-path options are reserved because MCServer sets them.
    """
    if not isinstance(arguments, tuple) or not all(isinstance(item, str) for item in arguments):
        raise InvalidServerConfiguration("Java arguments must be a sequence of strings.")
    if len(arguments) > MAX_JVM_ARGUMENTS:
        raise InvalidServerConfiguration(f"At most {MAX_JVM_ARGUMENTS} Java arguments are allowed.")
    for argument in arguments:
        if not argument or argument != argument.strip() or _has_control_characters(argument):
            raise InvalidServerConfiguration(f"Invalid Java argument: {argument!r}.")
        if len(argument) > MAX_JVM_ARGUMENT_LENGTH:
            raise InvalidServerConfiguration("A Java argument is too long.")
        if argument in _RESERVED_JVM_ARGUMENTS or argument.startswith(_RESERVED_JVM_PREFIXES):
            raise InvalidServerConfiguration(
                f"{argument} is set by MCServer (use the memory setting and the server JAR instead)."
            )
    return arguments


@dataclass(frozen=True, slots=True)
class ServerConfiguration:
    """What MCServer must remember to launch a server; no runtime state (ADR 0003, ADR 0007).

    ``directory`` is the server folder name relative to the managed servers
    root and ``jar_file`` the JAR name inside that folder. ``server_id`` never
    changes; ``display_name`` is what users rename. ``jvm_arguments`` are extra
    Java options; ``java_path`` overrides the Java executable for this server.
    ``server_type`` and ``minecraft_version`` are optional labels.
    """

    server_id: str
    directory: str
    jar_file: str
    memory_mb: int
    display_name: str = ""
    jvm_arguments: tuple[str, ...] = ()
    java_path: str | None = None
    server_type: str | None = None
    minecraft_version: str | None = None

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
        if not isinstance(self.display_name, str) or self.display_name != self.display_name.strip():
            raise InvalidServerConfiguration("The display name must not start or end with spaces.")
        if len(self.display_name) > MAX_DISPLAY_NAME_LENGTH or _has_control_characters(self.display_name):
            raise InvalidServerConfiguration(
                f"The display name must be at most {MAX_DISPLAY_NAME_LENGTH} printable characters."
            )
        validate_jvm_arguments(self.jvm_arguments)
        if self.java_path is not None and (
            not isinstance(self.java_path, str) or not self.java_path.strip() or _has_control_characters(self.java_path)
        ):
            raise InvalidServerConfiguration("The Java path must be a non-empty path.")
        for label, value in (("server type", self.server_type), ("Minecraft version", self.minecraft_version)):
            if value is not None and (
                not isinstance(value, str)
                or not value
                or len(value) > MAX_LABEL_LENGTH
                or _has_control_characters(value)
            ):
                raise InvalidServerConfiguration(f"Invalid {label}: {value!r}.")

    @property
    def name(self) -> str:
        """Return what the GUI shows: the display name, or the identifier when none is set."""
        return self.display_name or self.server_id
