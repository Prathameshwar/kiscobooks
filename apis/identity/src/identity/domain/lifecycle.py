"""Lifecycle transitions preserve history and terminal states."""

from billing_platform.errors import ConflictError


def assert_status_transition(current: str, requested: str, *, terminal: str) -> None:
    if current == terminal and requested != current:
        raise ConflictError("a terminal record cannot be reactivated")
