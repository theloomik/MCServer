"""Domain-specific exceptions."""


class InvalidStateTransition(ValueError):
    """Raised when a server lifecycle transition is not allowed."""
