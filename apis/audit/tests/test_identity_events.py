"""Identity's scoped audit payload survives ingestion and company-filtered retrieval."""

from __future__ import annotations

import uuid

import httpx
from billing_platform.outbox import audit_payload
from sqlalchemy.ext.asyncio import AsyncSession

from audit.tasks.consume import handle_event
from tests.api_support import actor_headers, grant
from tests.seed import audit_envelope


async def test_identity_event_is_visible_to_its_company_reader(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    company, actor = uuid.uuid4(), uuid.uuid4()
    envelope = audit_envelope(tenant_id=tenant_a)
    payload = audit_payload(
        action="company.updated",
        entity_type="company",
        entity_id=company,
        actor_user_id=actor,
        company_id=company,
        changes={"display_name": {"from": "[redacted]", "to": "[redacted]"}},
    )
    envelope = envelope.model_copy(update={"payload": payload})
    await handle_event(session, envelope, consumer_name="identity-review")
    await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=actor,
        grants=[grant(["audit.read"], scope_type="company", scope_id=company)],
    )
    response = await client.get(f"/v1/audit-events?company_id={company}", headers=headers)
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["company_id"] == str(company)
