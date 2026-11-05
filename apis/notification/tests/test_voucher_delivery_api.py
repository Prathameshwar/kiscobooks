"""Voucher delivery evidence is company-fenced and masked."""

import uuid

import httpx
import pytest
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from notification.tasks.consume import handle_send_command
from tests.api_support import actor_headers
from tests.notif_seed import CIPHER, KEY_REF, envelope, seed_email_route


@pytest.mark.asyncio
async def test_company_scoped_voucher_delivery_lookup(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
) -> None:
    company, voucher, subject = uuid7(), uuid7(), uuid7()
    await seed_email_route(
        session,
        tenant=tenant_a,
        company=company,
        subject=subject,
        event_key="voucher.sales_order.issued",
        subject_type="party_general",
        endpoint_company_id=company,
    )
    base = envelope(
        tenant_a,
        company,
        subject,
        event_key="voucher.sales_order.issued",
    )
    event = base.model_copy(
        update={
            "payload": base.payload
            | {
                "source_service": "vouchers",
                "aggregate_type": "voucher",
                "subject_type": "party_general",
                "aggregate_id": str(voucher),
            },
        }
    )
    result = await handle_send_command(
        session,
        event,
        cipher=CIPHER,
        key_ref=KEY_REF,
    )
    assert result.deliveries_created == 1
    await session.commit()
    allowed = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        company_id=company,
        permissions=["notification.request.read", "notification.delivery.read"],
    )
    requests = await client.get(
        f"/v1/companies/{company}/vouchers/{voucher}/requests",
        headers=allowed,
    )
    assert requests.status_code == 200, requests.text
    assert requests.json()["items"][0]["source_message_id"] == str(event.message_id)
    deliveries = await client.get(
        f"/v1/companies/{company}/vouchers/{voucher}/deliveries",
        headers=allowed,
    )
    assert deliveries.status_code == 200, deliveries.text
    assert len(deliveries.json()["items"]) == 1
    assert "@" in deliveries.json()["items"][0]["destination_masked"]
    other = await client.get(
        f"/v1/companies/{uuid.uuid4()}/vouchers/{voucher}/requests",
        headers=allowed,
    )
    assert other.status_code == 403
    assert (
        await client.get(
            f"/v1/companies/{company}/vouchers/{voucher}/requests",
        )
    ).status_code == 401
