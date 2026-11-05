"""Monotonic delivery state transitions, including out-of-order callbacks."""

from __future__ import annotations

from typing import Final

from billing_platform.errors import ConflictError, ValidationFailedError

from notification.domain.constants import DELIVERY_STATES

_PRECEDENCE: Final = {
    "pending": 0,
    "scheduled": 1,
    "retry_wait": 2,
    "sending": 3,
    "accepted": 4,
    "delivered": 5,
    "read": 6,
    "suppressed": 90,
    "failed": 90,
    "cancelled": 90,
    "expired": 90,
}
TERMINAL: Final = frozenset({"suppressed", "failed", "cancelled", "expired", "read"})


def should_advance(current: str, proposed: str) -> bool:
    if current not in DELIVERY_STATES or proposed not in DELIVERY_STATES:
        raise ValidationFailedError("unknown delivery state")
    if current in TERMINAL:
        return False
    return _PRECEDENCE[proposed] > _PRECEDENCE[current]


def require_transition(current: str, proposed: str) -> None:
    if not should_advance(current, proposed):
        raise ConflictError(f"delivery cannot advance from {current} to {proposed}")
