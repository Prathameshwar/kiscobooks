"""The audit category taxonomy and its retention floors (docs/audit.md §3, §6).

The set is reconciled to the emit contract in ``billing_platform.outbox.audit_payload``
— the operative one that identity and notification already publish through. Keeping a
second, drifting list here is exactly the bug the reconciliation fixed, so this mirrors
it and a test asserts the two never diverge.

``security`` is the separately gated surface (``audit.read_security``); the rest are
readable with ``audit.read``. Retention is by category (§6): the partition-drop job
keeps a month's partition until the *longest-lived* category in it has expired.
"""

from __future__ import annotations

from typing import Final

#: Every category an audit event may carry. Mirrors the emit contract.
CATEGORIES: Final[frozenset[str]] = frozenset(
    {"security", "money", "admin", "access", "system"}
)

#: Read gating (§5.1). ``security`` events are visible only with ``audit.read_security``;
#: everything else with ``audit.read``. The activity feed (``activity.read``) is a
#: separate, friendlier projection and never exposes ``security`` rows.
SECURITY_CATEGORY: Final[str] = "security"

#: Category → the ``Settings`` attribute holding its retention floor in days. A category
#: absent here would never expire; the ``CATEGORIES`` parity test forbids that.
RETENTION_SETTING_BY_CATEGORY: Final[dict[str, str]] = {
    "security": "retention_days_security",
    "money": "retention_days_money",
    "admin": "retention_days_admin",
    "access": "retention_days_access",
    "system": "retention_days_system",
}


def is_valid_category(category: str) -> bool:
    return category in CATEGORIES
