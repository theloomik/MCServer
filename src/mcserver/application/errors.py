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


class ServerStopFailed(RuntimeError):
    """Raised when a requested server shutdown cannot be completed."""

    def __init__(self, server_id: str) -> None:
        """Describe the server whose shutdown request failed."""
        self.server_id = server_id
        super().__init__(f"Could not stop server '{server_id}'.")
