"""HTTP tests for the attachment scan gate (Phase 9): only a clean attachment may be
attached to a delivery."""

from __future__ import annotations

import hashlib
import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import NotificationDelivery
from notification.tasks.consume import handle_send_command
from tests.api_support import actor_headers
from tests.notif_seed import CIPHER, KEY_REF, envelope, seed_email_route

pytestmark = pytest.mark.asyncio


def _headers(tenant: uuid.UUID) -> dict[str, str]:
    return actor_headers(
        tenant_id=tenant, user_id=uuid7(), permissions=["notification.template.manage"]
    )


async def _delivery_id(session: AsyncSession, tenant: uuid.UUID) -> uuid.UUID:
    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant, company=company, subject=subject)
    result = await handle_send_command(
        session, envelope(tenant, company, subject), cipher=CIPHER, key_ref=KEY_REF
    )
    await session.commit()
    with tenant_scope(tenant):
        row = (
            await session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.request_id == result.request_id
                )
            )
        ).one()
    return row.id


def _attachment_body() -> dict[str, object]:
    return {
        "storage_key": "s3://att/1",
        "filename": "invoice.pdf",
        "media_type": "application/pdf",
        "byte_size": 2048,
        "sha256_hex": hashlib.sha256(b"x").hexdigest(),
    }


async def test_external_attachment_transport_and_self_scanning_are_blocked(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    delivery_id = await _delivery_id(session, tenant_a)
    headers = _headers(tenant_a)

    created = await client.post("/v1/attachments", json=_attachment_body(), headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["scan_status"] == "pending"
    assert "filename" not in body  # filename is encrypted, never returned

    # Pending attachment cannot be attached yet.
    blocked = await client.post(
        f"/v1/deliveries/{delivery_id}/attachments",
        json={"attachment_id": body["id"], "disposition": "attachment"},
        headers=headers,
    )
    assert blocked.status_code == 409

    # Mark clean, then it attaches.
    scanned = await client.patch(
        f"/v1/attachments/{body['id']}/scan", json={"scan_status": "clean"}, headers=headers
    )
    assert scanned.status_code == 403
    ok = await client.post(
        f"/v1/deliveries/{delivery_id}/attachments",
        json={"attachment_id": body["id"], "disposition": "attachment"},
        headers=headers,
    )
    assert ok.status_code == 409


async def test_infected_attachment_is_refused(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    delivery_id = await _delivery_id(session, tenant_a)
    headers = _headers(tenant_a)
    created = await client.post("/v1/attachments", json=_attachment_body(), headers=headers)
    aid = created.json()["id"]
    await client.patch(
        f"/v1/attachments/{aid}/scan", json={"scan_status": "infected"}, headers=headers
    )
    resp = await client.post(
        f"/v1/deliveries/{delivery_id}/attachments",
        json={"attachment_id": aid, "disposition": "attachment"},
        headers=headers,
    )
    assert resp.status_code == 409
