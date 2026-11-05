"""Map a broker ``MessageEnvelope`` to ``audit_event`` field values (docs/audit.md §3).

Pure and framework-free: it validates and shapes, the consumer persists. The payload is
the emit contract in ``billing_platform.outbox.audit_payload`` — currently ``action``,
``category``, ``entity_type``, ``entity_id``, ``actor_user_id``, ``on_behalf_of_user_id``,
``changes`` and ``reason``. The remaining §3 columns are declared here too, defaulting to
``None``, so the day the emit contract is enriched the consumer picks them up with no
schema change (decision log, docs/audit.md §8).

``extra="forbid"`` even though the producer is a trusted internal service: a typo'd key
in an emitting service should surface as a rejected message on its dead-letter queue,
not vanish silently from the one record an auditor relies on.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any

from billing_platform.messages import MessageEnvelope
from pydantic import BaseModel, ConfigDict, Field, field_validator

from audit.domain.categories import CATEGORIES


class AuditEventPayload(BaseModel):
    """The validated body of an audit event, as emitted through the outbox."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(max_length=60)
    category: str
    entity_type: str = Field(max_length=80)
    entity_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    on_behalf_of_user_id: uuid.UUID | None = None
    changes: dict[str, Any] | None = None
    reason: str | None = Field(default=None, max_length=500)

    # Documented §3 columns not yet populated by the emit contract — nullable until it is
    # enriched. Declared so validation accepts them the moment they arrive.
    actor_type: str | None = Field(default=None, max_length=32)
    actor_ip: str | None = Field(default=None, max_length=45)
    actor_user_agent: str | None = Field(default=None, max_length=400)
    api_client_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    context: dict[str, Any] | None = None
    source_service: str | None = Field(default=None, max_length=40)
    request_id: str | None = Field(default=None, max_length=64)

    @field_validator("changes", "context")
    @classmethod
    def _json_evidence(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        # MySQL JSON rejects NaN/Infinity even though Python's JSON parser accepts them.
        # Permanent payload defects must dead-letter, not block the single chain writer.
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("audit evidence must contain finite JSON values") from exc
        return value

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError(f"unknown audit category: {value}")
        return value


def event_fields(envelope: MessageEnvelope, *, now: dt.datetime) -> dict[str, Any]:
    """Build the non-chain ``audit_event`` column values from ``envelope``.

    ``sequence``, ``prev_hash`` and ``row_hash`` are assigned by the chain writer, not
    here — this produces everything else. ``occurred_at`` is the envelope's source
    timestamp (§2.2); ``ingested_at`` is ``now`` (the consumer's receipt clock).
    """
    payload = AuditEventPayload.model_validate(envelope.payload)
    return {
        "tenant_id": envelope.tenant_id,
        "occurred_at": envelope.occurred_at,
        "message_id": envelope.message_id,
        "trace_id": envelope.trace_id,
        "ingested_at": now,
        "actor_type": payload.actor_type,
        "actor_user_id": payload.actor_user_id,
        "on_behalf_of_user_id": payload.on_behalf_of_user_id,
        "actor_ip": payload.actor_ip,
        "actor_user_agent": payload.actor_user_agent,
        "api_client_id": payload.api_client_id,
        "company_id": payload.company_id,
        "department_id": payload.department_id,
        "category": payload.category,
        "action": payload.action,
        "entity_type": payload.entity_type,
        "entity_id": payload.entity_id,
        "changes": payload.changes,
        "context": payload.context,
        "reason": payload.reason,
        "source_service": payload.source_service,
        "request_id": payload.request_id,
    }
