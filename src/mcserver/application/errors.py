"""Expected failures raised by application use cases."""


class ActiveServerAlreadyExists(RuntimeError):
    """Raised when a server start is requested while another server is active."""

    def __init__(self, active_server_id: str) -> None:
        """Describe the server that currently owns the active lifecycle."""
        self.active_server_id = active_server_id
        super().__init__(f"Server '{active_server_id}' is already active or starting.")


class ServerStartFailed(RuntimeError):
    """Raised when the server starter cannot accept a start request."""

    def __init__(self, server_id: str) -> None:
        """Describe the server whose start request failed."""
        self.server_id = server_id
        super().__init__(f"Could not start server '{server_id}'.")


class ServerConfigurationNotFound(LookupError):
    """Raised when no stored configuration has the requested server identifier."""

    def __init__(self, server_id: str) -> None:
        """Describe the missing server."""
        self.server_id = server_id
        super().__init__(f"Server configuration '{server_id}' does not exist.")


class ServerConfigurationAlreadyExists(RuntimeError):
    """Raised when adding a configuration whose server identifier is already stored."""

    def __init__(self, server_id: str) -> None:
        """Describe the conflicting server."""
        self.server_id = server_id
        super().__init__(f"Server configuration '{server_id}' already exists.")


class ServerDirectoryInUse(RuntimeError):
    """Raised when a configuration names a directory already used by another server."""

    def __init__(self, directory: str, owner_server_id: str) -> None:
        """Describe the directory and the server that already uses it."""
        self.directory = directory
        self.owner_server_id = owner_server_id
        super().__init__(f"Server directory '{directory}' is already used by server '{owner_server_id}'.")


class ServerConfigurationStorageError(RuntimeError):
    """Base for failures of the storage behind a configuration repository.

    Infrastructure adapters raise subclasses with technical detail; use cases
    can handle this type without knowing the storage technology.
    """


class LegacyConfigurationUnavailable(RuntimeError):
    """Raised when legacy configuration data exists but cannot be read at all.

    A legacy import stops without importing anything when this is raised.
    """


class LegacyServerEntryInvalid(ValueError):
    """Raised when one legacy server entry cannot be converted to a configuration."""

    def __init__(self, server_id: str, reason: str) -> None:
        """Describe the rejected entry and why."""
        self.server_id = server_id
        self.reason = reason
        super().__init__(f"Legacy server '{server_id}' is invalid: {reason}")


class ServerProvisioningError(RuntimeError):
    """Base for failures while preparing a server's files.

    ``leftovers`` lists paths, relative to the servers root, that the failed
    operation created but could not remove. It is empty when nothing was left
    behind.
    """

    def __init__(self, message: str, leftovers: tuple[str, ...] = ()) -> None:
        """Describe the failure and anything it left on disk."""
        self.leftovers = leftovers
        super().__init__(message)


class InvalidSourceJar(ServerProvisioningError):
    """Raised when the selected source is not an existing regular ``.jar`` file."""

    def __init__(self, source_jar: str, reason: str) -> None:
        """Describe the rejected source and why."""
        self.source_jar = source_jar
        self.reason = reason
        super().__init__(f"Cannot use '{source_jar}' as the server JAR: {reason}")


class UnsafeServerPath(ServerProvisioningError):
    """Raised when a directory or file name would resolve outside the servers root."""


class ServerDirectoryAlreadyExists(ServerProvisioningError):
    """Raised when the server directory (or anything with that name) already exists."""

    def __init__(self, directory: str) -> None:
        """Describe the existing directory; its contents are left untouched."""
        self.directory = directory
        super().__init__(f"Server directory '{directory}' already exists; it was not modified.")


class ServerJarAlreadyExists(ServerProvisioningError):
    """Raised when the destination JAR file already exists; it is never overwritten."""

    def __init__(self, directory: str, jar_file: str) -> None:
        """Describe the existing destination file."""
        self.directory = directory
        self.jar_file = jar_file
        super().__init__(f"'{directory}/{jar_file}' already exists; it was not overwritten.")


class ServerFilesystemError(ServerProvisioningError):
    """Raised when the operating system refuses or fails a provisioning step."""


class ProvisioningRollbackFailed(ServerProvisioningError):
    """Raised when provisioning failed and its own changes could not all be undone.

    ``original`` is the failure that triggered the rollback; ``leftovers``
    names what remains on disk and needs manual attention. Nothing that
    existed before the operation is ever removed.
    """

    def __init__(self, server_id: str, original: ServerProvisioningError, leftovers: tuple[str, ...]) -> None:
        """Describe the original failure and what was left behind."""
        self.server_id = server_id
        self.original = original
        left = ", ".join(leftovers)
        super().__init__(
            f"Provisioning server '{server_id}' failed ({original}) and could not be fully undone; left on disk: {left}.",
            leftovers,
        )


class ServerCreationRollbackFailed(RuntimeError):
    """Raised when server creation failed and its configuration record could not be removed.

    ``provisioning_error`` is the failure that triggered the rollback.
    ``rollback_error`` is why removing the record failed, or ``None`` when the
    record was deliberately kept because it had been changed by someone else
    in the meantime. The record for ``server_id`` may still exist and point to
    a server that was never fully provisioned.
    """

    def __init__(self, server_id: str, provisioning_error: Exception, rollback_error: Exception | None) -> None:
        """Describe both failures and the state left behind."""
        self.server_id = server_id
        self.provisioning_error = provisioning_error
        self.rollback_error = rollback_error
        reason = (
            f"removing it failed: {rollback_error}"
            if rollback_error is not None
            else "it was changed by another operation and was kept"
        )
        super().__init__(
            f"Creating server '{server_id}' failed ({provisioning_error}); its configuration record may still "
            f"exist because {reason}."
        )


class ServerStopFailed(RuntimeError):
    """Raised when a requested server shutdown cannot be completed."""

    def __init__(self, server_id: str) -> None:
        """Describe the server whose shutdown request failed."""
        self.server_id = server_id
        super().__init__(f"Could not stop server '{server_id}'.")
