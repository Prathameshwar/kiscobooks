"""Outbox writer.

Publishing goes through the outbox, never directly after commit (invariant 10).
RabbitMQ has no replay, so an event published after the transaction commits is
lost if the process dies in between — and an event published *before* it commits
is a lie if the transaction rolls back.

``emit`` only stages the row on the session. The caller's transaction commits it,
which is what makes the event and the business change atomic (invariant 8).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from billing_platform.audit_context import correlation
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7


def emit(
    session: AsyncSession | Session,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    tenant_id: uuid.UUID | None = None,
    trace_id: str | None = None,
    schema_version: int = 1,
    occurred_at: dt.datetime | None = None,
) -> Outbox:
    """Stage an event on the caller's session. Does **not** commit.

    ``message_id`` is generated here and is what consumers dedupe on, so a
    republish of the same row is idempotent downstream.
    """
    if not aggregate_type or not event_type:
        raise ValueError("aggregate_type and event_type are required")

    row = Outbox(
        id=uuid7(),
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        schema_version=schema_version,
        message_id=uuid7(),
        trace_id=trace_id or correlation()[0],
        occurred_at=occurred_at or utcnow(),
        available_at=utcnow(),
        attempt_count=0,
    )
    session.add(row)
    return row


def audit_payload(
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    category: str = "admin",
    changes: dict[str, Any] | None = None,
    on_behalf_of_user_id: uuid.UUID | None = None,
    reason: str | None = None,
    company_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Build an audit event payload.

    Holds ``actor_user_id`` and never denormalized PII (invariant 9). ``changes``
    carries field names and values for business columns only — never a token, a
    bank account, a password, or a full tax identifier. Company-owned commands
    pass their authoritative company ID; omission preserves the legacy payload.
    """
    if department_id is not None and company_id is None:
        raise ValueError("department audit scope requires a company")
    if category not in _AUDIT_CATEGORIES:
        raise ValueError(f"unknown audit category: {category}")
    from billing_platform.audit_context import resolve_actor

    actor_user_id, on_behalf_of_user_id = resolve_actor(actor_user_id, on_behalf_of_user_id)
    return {
        "action": action,
        "category": category,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "on_behalf_of_user_id": (str(on_behalf_of_user_id) if on_behalf_of_user_id else None),
        "changes": changes or {},
        "reason": reason,
        **({"company_id": str(company_id)} if company_id is not None else {}),
        **({"department_id": str(department_id)} if department_id is not None else {}),
        **({"request_id": correlation()[1]} if correlation()[1] is not None else {}),
    }


_AUDIT_CATEGORIES = frozenset({"admin", "security", "access", "money", "system"})
