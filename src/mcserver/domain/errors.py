"""Domain-specific exceptions."""


class InvalidStateTransition(ValueError):
    """Raised when a server lifecycle transition is not allowed."""


class InvalidServerConfiguration(ValueError):
    """Raised when server configuration values violate domain rules."""
