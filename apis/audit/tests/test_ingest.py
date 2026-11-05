"""The envelope → event-fields mapping and category taxonomy (docs/audit.md §3)."""

from __future__ import annotations

import uuid

import pytest
from billing_platform.db.types import utcnow
from billing_platform.outbox import _AUDIT_CATEGORIES, audit_payload
from pydantic import ValidationError

from audit.domain import categories
from audit.domain.ingest import AuditEventPayload, event_fields
from tests.seed import audit_envelope


def test_category_set_matches_the_emit_contract() -> None:
    # The one source of drift the reconciliation fixed (decision log) — asserted so it
    # cannot silently return.
    assert categories.CATEGORIES == _AUDIT_CATEGORIES


def test_event_fields_carries_envelope_provenance() -> None:
    tenant = uuid.uuid4()
    now = utcnow()
    envelope = audit_envelope(tenant_id=tenant, category="money", action="posted")
    fields = event_fields(envelope, now=now)
    assert fields["tenant_id"] == tenant
    assert fields["occurred_at"] == envelope.occurred_at
    assert fields["message_id"] == envelope.message_id
    assert fields["ingested_at"] == now
    assert fields["category"] == "money"


def test_unknown_category_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AuditEventPayload.model_validate(
            {"action": "x", "category": "bogus", "entity_type": "user"}
        )


def test_extra_key_is_rejected() -> None:
    # A typo in an emitting service must dead-letter, not vanish from the record.
    with pytest.raises(ValidationError):
        AuditEventPayload.model_validate(
            {"action": "x", "category": "admin", "entity_type": "user", "typ" "o": 1}
        )


def test_future_enrichment_fields_are_accepted() -> None:
    payload = AuditEventPayload.model_validate(
        {
            "action": "logged_in",
            "category": "security",
            "entity_type": "user",
            "actor_ip": "203.0.113.5",
            "source_service": "identity",
            "company_id": str(uuid.uuid4()),
        }
    )
    assert payload.actor_ip == "203.0.113.5"
    assert payload.source_service == "identity"


def test_catalog_company_scope_from_shared_producer_survives_ingestion() -> None:
    tenant, company, actor, entity = (uuid.uuid4() for _ in range(4))
    envelope = audit_envelope(tenant_id=tenant)
    payload = audit_payload(
        action="catalog.item_group.create",
        entity_type="catalog.item_group",
        entity_id=entity,
        actor_user_id=actor,
        company_id=company,
    )
    fields = event_fields(envelope.model_copy(update={"payload": payload}), now=utcnow())
    assert fields["company_id"] == company and fields["tenant_id"] == tenant
    assert fields["actor_user_id"] == actor and fields["entity_id"] == entity


@pytest.mark.parametrize(
    "field,limit",
    [
        ("action", 60),
        ("entity_type", 80),
        ("reason", 500),
        ("actor_type", 32),
        ("actor_ip", 45),
        ("actor_user_agent", 400),
        ("source_service", 40),
        ("request_id", 64),
    ],
)
def test_payload_strings_fit_the_persisted_contract(field: str, limit: int) -> None:
    body = {"action": "company.updated", "category": "admin", "entity_type": "company"}
    AuditEventPayload.model_validate(body | {field: "x" * limit})
    with pytest.raises(ValidationError):
        AuditEventPayload.model_validate(body | {field: "x" * (limit + 1)})
