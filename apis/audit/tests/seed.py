"""Builders for the broker envelopes the ingestion consumer eats.

A test event is exactly what an emitting service would stage on its outbox: a
``MessageEnvelope`` whose payload is ``billing_platform.outbox.audit_payload`` output. This
keeps the tests honest against the real emit contract rather than a hand-rolled shape.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.outbox import audit_payload


def audit_envelope(
    *,
    tenant_id: uuid.UUID,
    action: str = "created",
    category: str = "admin",
    entity_type: str = "user",
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    changes: dict[str, Any] | None = None,
    occurred_at: dt.datetime | None = None,
    message_id: uuid.UUID | None = None,
    event_type: str = "identity.user.created",
) -> MessageEnvelope:
    payload = audit_payload(
        action=action,
        category=category,
        entity_type=entity_type,
        entity_id=entity_id or uuid7(),
        actor_user_id=actor_user_id or uuid7(),
        changes=changes,
    )
    if company_id is not None:
        payload = payload | {"company_id": str(company_id)}
    if department_id is not None:
        payload = payload | {"department_id": str(department_id)}
    return MessageEnvelope(
        message_id=message_id or uuid7(),
        tenant_id=tenant_id,
        event_type=event_type,
        schema_version=1,
        occurred_at=occurred_at or utcnow(),
        trace_id=None,
        payload=payload,
    )
