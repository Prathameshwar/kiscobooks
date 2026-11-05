from __future__ import annotations

from typing import Final

CHANNELS: Final = frozenset({"email", "sms", "whatsapp", "push"})
CATEGORIES: Final = frozenset({"security", "transactional", "operational", "marketing"})
DELIVERY_STATES: Final = frozenset(
    {
        "pending",
        "scheduled",
        "suppressed",
        "sending",
        "accepted",
        "delivered",
        "read",
        "retry_wait",
        "failed",
        "cancelled",
        "expired",
    }
)
ATTEMPT_OUTCOMES: Final = frozenset(
    {"in_progress", "accepted", "retryable_failure", "permanent_failure", "unknown"}
)
