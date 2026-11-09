"""Validates the create-server form and runs ``ServerCreation`` in the background."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePath

from PySide6.QtCore import QObject, Signal

from mcserver.application.errors import ServerConfigurationStorageError
from mcserver.application.server_creation import ServerCreation
from mcserver.application.server_management import ServerManagement
from mcserver.application.server_provisioning import ProvisionedServer
from mcserver.domain.server_configuration import MAX_MEMORY_MB, MIN_MEMORY_MB, is_safe_name
from mcserver.presentation.errors import UserMessage, describe_error
from mcserver.presentation.workers import BackgroundRunner

_logger = logging.getLogger(__name__)

DEFAULT_MEMORY_MB = 4096
FIELDS = ("server_id", "directory", "source_jar", "memory_mb")


@dataclass(frozen=True, slots=True)
class CreationForm:
    """What the user entered. ``source_jar`` is the path chosen in the file dialog."""

    server_id: str = ""
    directory: str = ""
    source_jar: str = ""
    memory_mb: int = DEFAULT_MEMORY_MB

    @property
    def jar_file(self) -> str:
        """The JAR name inside the server folder: the selected file's name (nothing to type twice)."""
        return PurePath(self.source_jar).name if self.source_jar else ""


@dataclass(frozen=True, slots=True)
class FormValidation:
    """Per-field message keys; an empty mapping means the form can be submitted."""

    errors: Mapping[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Return whether every field is valid."""
        return not self.errors


@dataclass(frozen=True, slots=True)
class CreationState:
    """Progress of the current submission."""

    busy: bool = False
    error: UserMessage | None = None


class ServerCreationController(QObject):
    """Check the form against domain rules and stored servers, then call ``ServerCreation``.

    Validation reuses the domain's name and memory rules and the stored
    configurations (duplicate ID, directory already used by another server).
    Conflicts on disk, the source file itself and rollback are the backend's
    job: it reports them as errors, which are shown as they are.
    """

    state_changed = Signal(object)  # CreationState
    created = Signal(object)  # ServerConfiguration

    def __init__(
        self,
        server_creation: ServerCreation,
        management: ServerManagement,
        runner: BackgroundRunner,
        parent: QObject | None = None,
    ) -> None:
        """Create servers through ``server_creation``; read existing ones through ``management``."""
        super().__init__(parent)
        self._server_creation = server_creation
        self._management = management
        self._runner = runner
        self._state = CreationState()
        self._taken_ids: frozenset[str] = frozenset()
        self._taken_directories: dict[str, str] = {}

    @property
    def state(self) -> CreationState:
        """Return the current progress."""
        return self._state

    @property
    def busy(self) -> bool:
        """Return whether a creation is running."""
        return self._state.busy

    def begin(self) -> None:
        """Prepare a new form: forget old errors and read the stored servers once."""
        if self._state.busy:
            return
        self._load_existing()
        self._publish(CreationState())

    def validate(self, form: CreationForm) -> FormValidation:
        """Return message keys for invalid fields (cheap; called while the user types)."""
        errors: dict[str, str] = {}
        server_id = form.server_id.strip()
        if not server_id:
            errors["server_id"] = "create.error.server_id_required"
        elif server_id != form.server_id or not is_safe_name(server_id):
            errors["server_id"] = "create.error.server_id_invalid"
        elif server_id in self._taken_ids:
            errors["server_id"] = "create.error.server_id_taken"

        directory = form.directory
        if not directory.strip():
            errors["directory"] = "create.error.directory_required"
        elif not is_safe_name(directory):
            errors["directory"] = "create.error.directory_invalid"
        elif directory.casefold() in self._taken_directories:
            errors["directory"] = "create.error.directory_taken"

        if not form.source_jar:
            errors["source_jar"] = "create.error.jar_required"
        elif not form.jar_file.lower().endswith(".jar") or not is_safe_name(form.jar_file):
            errors["source_jar"] = "create.error.jar_invalid"

        if not MIN_MEMORY_MB <= form.memory_mb <= MAX_MEMORY_MB:
            errors["memory_mb"] = "create.error.memory_range"
        return FormValidation(errors)

    def taken_directory_owner(self, directory: str) -> str | None:
        """Return the server that already uses ``directory``, if any."""
        return self._taken_directories.get(directory.casefold())

    def submit(self, form: CreationForm) -> bool:
        """Start creating the server; return ``False`` if busy or the form is invalid."""
        if self._state.busy:
            return False
        self._load_existing()  # another window or process may have added servers meanwhile
        if not self.validate(form).ok:
            return False
        creation = self._server_creation

        def create() -> ProvisionedServer:
            return creation.create_server(
                server_id=form.server_id,
                directory=form.directory,
                jar_file=form.jar_file,
                memory_mb=form.memory_mb,
                source_jar=form.source_jar,
            )

        self._publish(CreationState(busy=True))
        self._runner.run(create, self._succeeded, self._failed)
        return True

    def _succeeded(self, result: ProvisionedServer) -> None:
        self._publish(CreationState())
        self.created.emit(result.configuration)

    def _failed(self, error: BaseException) -> None:
        message = describe_error(error)
        _logger.error("Creating a server failed:\n%s", message.details)
        self._load_existing()
        self._publish(CreationState(error=message))

    def _load_existing(self) -> None:
        try:
            servers = self._management.list_servers()
        except ServerConfigurationStorageError:
            _logger.exception("Could not read existing servers; the backend will still reject duplicates.")
            servers = ()
        self._taken_ids = frozenset(server.server_id for server in servers)
        self._taken_directories = {server.directory.casefold(): server.server_id for server in servers}

    def _publish(self, state: CreationState) -> None:
        self._state = state
        self.state_changed.emit(state)
