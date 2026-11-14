"""Application ports implemented by infrastructure adapters."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from mcserver.domain.server_configuration import ServerConfiguration

ProcessExitHandler = Callable[[int], None]


class OutputStream(Enum):
    """Where a console line came from."""

    STDOUT = "stdout"
    STDERR = "stderr"
    COMMAND = "command"
    """A console command sent by the user, echoed into the output."""


@dataclass(frozen=True, slots=True)
class ServerOutputLine:
    """One console line produced by a server process.

    ``sequence`` increases monotonically per output buffer so consumers can
    order lines and discard duplicates after a replay.
    """

    sequence: int
    server_id: str
    stream: OutputStream
    text: str


ServerOutputListener = Callable[[ServerOutputLine], None]
ProcessOutputHandler = Callable[[OutputStream, str], None]


class ServerOutputSink(Protocol):
    """Receive console lines from a running server process."""

    def publish(self, server_id: str, stream: OutputStream, text: str) -> None:
        """Record one console line without its trailing newline."""


class ServerRunner(Protocol):
    """Run one server process without exposing process APIs to use cases.

    The runner reports events and never decides lifecycle states: the
    coordinator owns ``ServerState`` (ADR 0005). ``on_output`` and ``on_exit``
    are called from background threads; ``on_exit`` runs once, after all output.
    """

    @property
    def process_id(self) -> int | None:
        """Return the operating-system process id after a successful start."""

    def start(self, server_id: str, on_exit: ProcessExitHandler, on_output: ProcessOutputHandler | None = None) -> None:
        """Start ``server_id``; report each console line to ``on_output`` and the exit code to ``on_exit``."""

    def send_command(self, command: str) -> None:
        """Write one console command line; raise ``ServerCommandFailed`` if input is closed."""

    def stop(self, timeout: float) -> bool:
        """Send ``stop`` and wait up to ``timeout`` seconds; return whether the process exited.

        Never forces termination: an unfinished stop leaves the process running (ADR 0006).
        """

    def wait_for_exit(self, timeout: float) -> bool:
        """Wait up to ``timeout`` seconds without sending anything; return whether the process exited."""

    def kill(self) -> None:
        """Terminate the process immediately and wait briefly for it (an explicit user decision only)."""

    def output_tail(self, limit: int = 40) -> tuple[str, ...]:
        """Return the last ``limit`` console lines (stdout and stderr) in arrival order."""


@dataclass(frozen=True, slots=True)
class StartOptions:
    """User decisions that change how a start is checked."""

    allow_outdated_java: bool = False
    """Start even though the Java found is older than the verified requirement."""


@dataclass(frozen=True, slots=True)
class LaunchWarning:
    """A condition the user should know about that did not block the start.

    ``code`` is stable (it selects a message key); ``params`` hold display values.
    """

    code: str
    params: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PreparedLaunch:
    """A runner ready to start, plus warnings from the launch checks."""

    runner: ServerRunner
    warnings: tuple[LaunchWarning, ...] = ()


class ServerRunnerFactory(Protocol):
    """Check a server's launch preconditions and create its runner.

    Raises ``EulaNotAccepted``, ``JavaNotFound``, ``JavaVersionTooOld`` or
    ``ServerWorldInUse`` when the server must not start.
    """

    def create(self, server_id: str, options: StartOptions) -> PreparedLaunch:
        """Return a runner configured for ``server_id``."""


Cancel = Callable[[], None]


class Scheduler(Protocol):
    """Run a callback later; injectable so timeouts can be tested without waiting."""

    def call_later(self, delay: float, callback: Callable[[], None]) -> Cancel:
        """Call ``callback`` after ``delay`` seconds (from any thread) unless cancelled first."""


@dataclass(frozen=True, slots=True)
class SessionMarker:
    """A running-server marker found on disk."""

    server_id: str
    started_at: str
    """ISO-8601 time the server was started, as recorded."""


class SessionMarkerStore(Protocol):
    """Remember which server is running so an unclean end can be detected on the next launch.

    A marker is written when a server process starts and removed when the
    application observes that process exit. A marker left behind means the
    application itself ended first (crash, forced end, or power loss).
    """

    def write(self, server_id: str, process_id: int | None) -> None:
        """Record that ``server_id`` is running."""

    def clear(self, server_id: str) -> None:
        """Remove ``server_id``'s marker; a missing marker is ignored."""

    def leftovers(self) -> tuple[SessionMarker, ...]:
        """Return the markers present right now."""


@dataclass(frozen=True, slots=True)
class JavaInstallation:
    """A Java executable that ran ``-version`` successfully."""

    executable: str
    major_version: int
    source: str
    """Where it was found: ``configured``, ``bundled``, ``java_home``, ``path`` or ``installed``."""


class JavaRuntimeProvider(Protocol):
    """Find Java runtimes on demand (every start), honouring a user-chosen executable."""

    def find(self, minimum_major: int | None = None) -> JavaInstallation:
        """Return the configured Java, else the best one found; raise ``JavaNotFound`` if none runs.

        With ``minimum_major``, a runtime meeting it is preferred over the first
        one found. A configured executable is always returned as it is.
        """

    def configure(self, executable: str | None) -> JavaInstallation | None:
        """Use ``executable`` for later starts (``None`` returns to automatic detection).

        Raises ``InvalidJavaExecutable`` if it does not run.
        """

    @property
    def configured_executable(self) -> str | None:
        """Return the executable chosen by the user, if any."""


class ServerConfigurationRepository(Protocol):
    """Store server configurations by ``server_id``.

    ``get``, ``update`` and ``remove`` raise ``ServerConfigurationNotFound``
    for an unknown identifier; ``add`` raises ``ServerConfigurationAlreadyExists``
    for a taken one. ``add`` and ``update`` raise ``ServerDirectoryInUse`` when
    another server already uses the same directory (compared case-insensitively,
    as on Windows). Storage failures raise ``ServerConfigurationStorageError``.
    """

    def list_all(self) -> tuple[ServerConfiguration, ...]:
        """Return every stored configuration in a stable order."""

    def get(self, server_id: str) -> ServerConfiguration:
        """Return the configuration stored for ``server_id``."""

    def add(self, configuration: ServerConfiguration) -> None:
        """Store a configuration for a new server."""

    def update(self, configuration: ServerConfiguration) -> None:
        """Replace the stored configuration with the same ``server_id``."""

    def remove(self, server_id: str) -> None:
        """Delete the configuration stored for ``server_id``."""


class LegacyServerConfigurationSource(Protocol):
    """Read-only access to server configurations kept in the legacy format.

    ``list_server_ids`` raises ``LegacyConfigurationUnavailable`` when legacy
    data exists but cannot be read, and returns an empty tuple when there is
    none. ``read_server`` raises ``LegacyServerEntryInvalid`` (or the domain's
    ``InvalidServerConfiguration``) for an entry that cannot be converted.
    """

    def list_server_ids(self) -> tuple[str, ...]:
        """Return the identifiers of all legacy server entries, in source order."""

    def read_server(self, server_id: str) -> ServerConfiguration:
        """Convert one legacy entry into a configuration."""


class ServerProvisioningFilesystem(Protocol):
    """Prepare server files inside the managed servers root.

    ``directory`` and ``jar_file`` are names relative to the root, as stored in
    ``ServerConfiguration``; ``source_jar`` is a path chosen by the user. All
    failures raise ``ServerProvisioningError`` subclasses. An operation that
    fails cleans up what it created itself; whatever it could not remove is
    reported in the error's ``leftovers``.
    """

    def check_source_jar(self, source_jar: str) -> None:
        """Raise ``InvalidSourceJar`` unless ``source_jar`` is an existing regular ``.jar`` file."""

    def create_directory(self, directory: str) -> None:
        """Create a new, empty server directory.

        Raises ``ServerDirectoryAlreadyExists`` if anything with that name exists.
        """

    def install_jar(self, directory: str, jar_file: str, source_jar: str) -> None:
        """Copy ``source_jar`` to ``directory/jar_file`` without overwriting.

        Raises ``ServerJarAlreadyExists`` if the destination exists. A partial
        copy is removed on failure.
        """

    def remove_created_directory(self, directory: str) -> None:
        """Remove a directory created by ``create_directory``, only if it is still empty."""

    def accept_eula(self, directory: str) -> None:
        """Write ``eula=true`` to ``directory/eula.txt`` atomically; call only after the user consented."""

    def eula_accepted(self, directory: str) -> bool:
        """Return whether ``directory/eula.txt`` contains ``eula=true``."""

    def remove_eula(self, directory: str) -> None:
        """Remove ``eula.txt`` written by ``accept_eula`` while a provisioning is rolled back."""
