"""Explicit value allowlist for durable platform administrative evidence."""

import re
import uuid
from typing import Any

_STATES = frozenset(
    {
        "active",
        "suspended",
        "closed",
        "pending",
        "approved",
        "rejected",
        "queued",
        "completed",
        "blocked",
        "invited",
        "approve",
        "reject",
        "reopen",
    }
)


def _safe(key: str, value: Any) -> bool:
    if key in {"status", "action"}:
        return isinstance(value, str) and value in _STATES
    if key in {"attested", "needs_attention", "provider_active", "provider_verified", "is_active"}:
        return type(value) is bool
    if key in {"count", "version"}:
        return type(value) is int and 0 <= value <= 2**63 - 1
    if key in {"added_grants", "removed_grants"}:
        return type(value) is int and 0 <= value <= 2**63 - 1
    if key == "catalogue_digest":
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    if key in {"command_id", "administrator_id", "assignment_id"}:
        try:
            return isinstance(value, str) and str(uuid.UUID(value)) == value
        except ValueError:
            return False
    if key == "kind":
        return value in ("country", "state", "currency", "language")
    if key == "delivery":
        return value in ("link", "email")
    if key == "code":
        return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9-]{2,6}", value) is not None
    if key == "error_code":
        return value in ("provider_unavailable", "profile_changed")
    return False


def safe_changes(changes: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in changes.items():
        if isinstance(value, dict) and set(value) <= {"from", "to"} and value:
            safe = all(_safe(key, part) for part in value.values())
        else:
            safe = _safe(key, value)
        result[key] = value if safe else {"changed": True}
    return result
