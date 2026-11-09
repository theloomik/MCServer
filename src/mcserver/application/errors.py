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


class ServerStopFailed(RuntimeError):
    """Raised when a requested server shutdown cannot be completed."""

    def __init__(self, server_id: str) -> None:
        """Describe the server whose shutdown request failed."""
        self.server_id = server_id
        super().__init__(f"Could not stop server '{server_id}'.")
