from __future__ import annotations

import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.tasks.audit_publisher import AUDIT_EVENT_TYPES
from tests.test_control import headers


async def test_mutation_audit_contract_is_safe_and_publishable(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    response = await client.post(
        "/v1/provider-accounts",
        headers=headers(tenant_a),
        json={
            "key": "safe",
            "channel": "email",
            "provider_key": "ses",
            "display_name": "private account label",
            "credential_ref": "env:PRIVATE",
            "callback_key": "s" * 43,
        },
    )
    assert response.status_code == 201
    with tenant_scope(tenant_a):
        events = list(await session.scalars(select(Outbox)))
        assert events and all(event.event_type in AUDIT_EVENT_TYPES for event in events)
        for event in events:
            assert event.payload["source_service"] == "notification"
            assert event.payload["context"]["notification_realm"] == "tenant"
            assert event.payload["action"] == event.event_type
            assert "env:PRIVATE" not in str(event.payload)
            assert "private account label" not in str(event.payload)
            assert "fields" not in event.payload["changes"]
            assert "values" not in event.payload["changes"]
            assert event.payload["actor_type"] == "user"
            if event.event_type == "notification.provider_account.created":
                assert event.payload["changes"]["credential_ref"] == {"changed": True}


async def test_all_company_template_history_is_tenant_wide(client, session, tenant_a):
    from billing_platform.constants import SCOPE_ALL

    result = await client.post(
        "/v1/templates",
        headers=headers(tenant_a),
        json={
            "company_id": str(SCOPE_ALL),
            "key": "tenant-wide-history",
            "event_key": "voucher.shared",
            "category": "transactional",
            "default_locale": "en",
        },
    )
    assert result.status_code == 201
    with tenant_scope(tenant_a):
        rows = list(
            await session.scalars(
                select(Outbox).where(
                    Outbox.event_type == "notification.notification_template.created"
                )
            )
        )
        assert len(rows) == 1 and "company_id" not in rows[0].payload
        assert rows[0].payload["context"]["notification_realm"] == "tenant"
