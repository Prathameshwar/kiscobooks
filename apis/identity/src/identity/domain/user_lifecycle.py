"""Deactivating a user — anonymize, never delete (CLAUDE.md invariant 12).

A user who has posted a document is referenced from the ledger forever, so the row
must survive deactivation with its PII replaced by a tombstone. ``id`` and
``employee_code`` are preserved deliberately: they are what keeps the surviving audit
trail and the tenant's own HR handle resolvable after the name and email are gone
(docs/identity-schema.md §4.1).

No framework and no ORM here (CLAUDE.md §4): the caller passes the ``user_id`` and gets
back the field values to write, so the rule is tested with no database.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any


def tombstone_values(
    user_id: uuid.UUID, *, deactivated_by: uuid.UUID, now: dt.datetime, reason: str | None
) -> dict[str, Any]:
    """The columns to overwrite when a user is deactivated.

    ``email`` becomes a per-id ``@invalid`` placeholder so the ``(tenant_id, email)``
    unique key still holds — two deactivated users must not collide on a shared
    tombstone. ``authentik_sub`` is cleared so the dead account can never resolve a
    login, and ``status`` moves to the terminal ``deactivated``.
    """
    return {
        "status": "deactivated",
        "authentik_sub": None,
        "salutation": None,
        "first_name": "[deactivated]",
        "middle_name": None,
        "last_name": None,
        "display_name": "Deactivated user",
        "email": f"deactivated+{user_id}@invalid",
        "email_verified_at": None,
        "phone_country_code": None,
        "phone": None,
        "phone_verified_at": None,
        "anonymized_at": now,
        "deactivated_at": now,
        "deactivated_by": deactivated_by,
        "deactivation_reason": reason,
    }
