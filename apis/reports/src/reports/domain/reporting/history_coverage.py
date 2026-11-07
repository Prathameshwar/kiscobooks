"""Unsupported report periods are distinct from accounting snapshot corruption."""

from billing_platform.errors import ConflictError


class InsufficientHistoryError(ConflictError):
    """The requested period has neither retained detail nor eligible imported YTD."""
