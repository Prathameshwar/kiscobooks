"""Accounting evidence cannot bypass the reader's current field policy."""

import base64
import hashlib
import hmac
import json
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.messages import MessageEnvelope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from audit.tasks.consume import handle_event
from tests.api_support import ACTOR_SECRET, actor_headers, grant


@pytest.mark.parametrize("entity", ["accounting.party", "catalog.item", "vouchers.voucher"])
async def test_business_evidence_requires_policy_context_and_honors_denies(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    entity: str,
) -> None:
    company, user = uuid.uuid4(), uuid.uuid4()
    now = utcnow()
    envelope = MessageEnvelope(
        message_id=uuid.uuid4(),
        tenant_id=tenant_a,
        event_type=entity + ".update",
        schema_version=1,
        occurred_at=now,
        payload={
            "action": entity + ".update",
            "category": "admin",
            "entity_type": entity,
            "entity_id": str(uuid.uuid4()),
            "company_id": str(company),
            "changes": {"country_code": {"from": "IN", "to": "US"}},
            "context": {"count": 1, "country_code": "private historical value"},
            "reason": "private historical reason",
        },
    )
    with tenant_scope(tenant_a):
        async with factory() as db, db.begin():
            receipt = await handle_event(db, envelope, consumer_name="audit-reads")
    headers = actor_headers(
        tenant_id=tenant_a, user_id=user, grants=[grant(["audit.read", "audit.export"])]
    )
    path = f"/v1/audit-events/{receipt.event_id}?occurred_at={now.isoformat()}"
    # URL params must preserve timezone '+' encoding.
    response = await client.get(
        path.split("?")[0], params={"occurred_at": now.isoformat()}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["changes"] == {}
    assert response.json()["context"] == {"count": 1}
    assert response.json()["reason"] is None
    body = json.loads(base64.urlsafe_b64decode(headers["X-Actor-Context"] + "=="))
    body["field_policies"] = [
        {
            "entity_type": entity,
            "field_key": "country_code",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(company),
            "conditional": True,
        }
    ]
    raw = json.dumps(body).encode()
    headers["X-Actor-Context"] = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    headers["X-Actor-Signature"] = hmac.new(ACTOR_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    response = await client.get(
        path.split("?")[0], params={"occurred_at": now.isoformat()}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["changes"] == {}
    assert response.json()["context"] == {"count": 1}
    assert response.json()["reason"] is None
    body["field_policies"] = []
    raw = json.dumps(body).encode()
    headers["X-Actor-Context"] = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    headers["X-Actor-Signature"] = hmac.new(ACTOR_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    response = await client.get(
        path.split("?")[0], params={"occurred_at": now.isoformat()}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["changes"]["country_code"] == {"from": "IN", "to": "US"}
    exported = await client.post(
        "/v1/audit-events/export", params={"company_id": str(company)}, headers=headers
    )
    assert exported.status_code == 200
    evidence = exported.json()["events"][0]
    assert evidence["context"] == {"count": 1} and evidence["reason"] is None
    assert evidence["row_hash"] == response.json()["row_hash"]


async def test_detail_rejects_context_verified_for_different_company(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company = uuid.uuid4()
    now = utcnow()
    with tenant_scope(tenant_a):
        async with factory() as db, db.begin():
            receipt = await handle_event(
                db,
                MessageEnvelope(
                    message_id=uuid.uuid4(),
                    tenant_id=tenant_a,
                    event_type="accounting.party.update",
                    schema_version=1,
                    occurred_at=now,
                    payload={
                        "action": "accounting.party.update",
                        "category": "admin",
                        "entity_type": "accounting.party",
                        "entity_id": str(uuid.uuid4()),
                        "company_id": str(company),
                    },
                ),
                consumer_name="audit-scope",
            )
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid.uuid4(), grants=[grant(["audit.read"])]
    )
    raw = json.loads(base64.urlsafe_b64decode(headers["X-Actor-Context"] + "=="))
    raw["audit_scope"] = {"company_id": str(uuid.uuid4())}
    encoded = json.dumps(raw).encode()
    headers["X-Actor-Context"] = base64.urlsafe_b64encode(encoded).decode().rstrip("=")
    headers["X-Actor-Signature"] = hmac.new(
        ACTOR_SECRET.encode(), encoded, hashlib.sha256
    ).hexdigest()
    response = await client.get(
        f"/v1/audit-events/{receipt.event_id}",
        params={"occurred_at": now.isoformat()},
        headers=headers,
    )
    assert response.status_code == 403


def test_catalog_parent_evidence_cannot_bypass_child_field_denies() -> None:
    from billing_platform.gateway import Actor, ReadPolicyContext

    from audit.api.evidence import visible_changes
    from audit.models import AuditEvent

    company = uuid.uuid4()
    current = Actor(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        grants=(),
        field_policies=(
            ReadPolicyContext(
                entity_type="catalog.product_numeric_default",
                field_key="quantity",
                effect="deny",
                scope_type="company",
                scope_id=company,
            ),
        ),
    )
    event = AuditEvent(
        entity_type="catalog.product_configuration_draft",
        company_id=company,
        changes={"quantity": {"changed": True}, "status": {"from": "DRAFT", "to": "PUBLISHED"}},
    )
    assert visible_changes(event, current) == {}


def test_voucher_parent_evidence_cannot_bypass_item_field_denies() -> None:
    from billing_platform.gateway import Actor, ReadPolicyContext

    from audit.api.evidence import visible_changes
    from audit.models import AuditEvent

    company = uuid.uuid4()
    current = Actor(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        grants=(),
        field_policies=(
            ReadPolicyContext(
                entity_type="vouchers.voucher_item",
                field_key="custom_secret",
                effect="deny",
                scope_type="company",
                scope_id=company,
            ),
        ),
    )
    event = AuditEvent(
        entity_type="vouchers.voucher",
        company_id=company,
        changes={"custom_secret": {"changed": True}, "status": {"to": "APPROVED"}},
    )
    assert visible_changes(event, current) == {}


def test_catalog_custom_field_marker_uses_its_policy_key() -> None:
    from billing_platform.gateway import Actor, ReadPolicyContext

    from audit.api.evidence import visible_changes
    from audit.models import AuditEvent

    company = uuid.uuid4()
    actor = Actor(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        field_policies=(
            ReadPolicyContext(
                entity_type="catalog.item",
                field_key="cf_private",
                effect="deny",
                scope_type="company",
                scope_id=company,
            ),
        ),
    )
    event = AuditEvent(
        entity_type="catalog.item",
        company_id=company,
        changes={"custom_field:cf_private": {"changed": True}, "name": {"changed": True}},
    )
    assert visible_changes(event, actor) == {"name": {"changed": True}}


@pytest.mark.parametrize(
    "context,expected",
    [
        (None, None),
        ({"count": True, "format": "CSV"}, {"format": "CSV"}),
        ({"count": 2, "format": "XLSX", "private": "secret"}, {"count": 2, "format": "XLSX"}),
        ({"count": 99999, "format": "unknown"}, {}),
    ],
)
def test_catalog_report_metadata_is_allowlisted(context, expected) -> None:
    from audit.api.evidence import visible_context
    from audit.models import AuditEvent

    event = AuditEvent(
        entity_type="catalog.bulk_job", action="catalog.bulk_job.export", context=context
    )
    assert visible_context(event) == expected


def test_catalog_historical_policy_ignores_unrelated_and_conditional_allows() -> None:
    from billing_platform.gateway import Actor, ReadPolicyContext

    from audit.api.evidence import visible_changes
    from audit.models import AuditEvent

    company = uuid.uuid4()
    base = {
        "entity_type": "catalog.item",
        "field_key": "status",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": company,
    }
    rules = (
        ReadPolicyContext(**(base | {"entity_type": "catalog.unit_of_measure"})),
        ReadPolicyContext(**(base | {"effect": "allow", "conditional": True})),
        ReadPolicyContext(
            **(base | {"subject_scope_type": "company", "subject_scope_id": uuid.uuid4()})
        ),
    )
    actor = Actor(tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), field_policies=rules)
    event = AuditEvent(
        entity_type="catalog.item",
        company_id=company,
        changes={"status": {"from": "DRAFT", "to": "ACTIVE"}},
    )
    assert visible_changes(event, actor) == event.changes


@pytest.mark.parametrize("same_company", [True, False])
def test_group_hierarchy_marker_respects_child_parent_denial(same_company: bool) -> None:
    from billing_platform.gateway import Actor, ReadPolicyContext

    from audit.api.evidence import visible_changes
    from audit.models import AuditEvent

    company = uuid.uuid4()
    actor = Actor(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        field_policies=(
            ReadPolicyContext(
                entity_type="catalog.item_group_parent",
                field_key="parent_group_id",
                effect="deny",
                scope_type="company",
                scope_id=company if same_company else uuid.uuid4(),
            ),
        ),
    )
    event = AuditEvent(
        entity_type="catalog.item_group",
        company_id=company,
        changes={"hierarchy": {"changed": True}},
    )
    assert visible_changes(event, actor) == ({} if same_company else event.changes)
