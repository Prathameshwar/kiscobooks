"""Terminal voucher events cancel pending sends, including late arrivals."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import NotificationDelivery, VoucherSendState
from notification.tasks.consume import handle_send_command
from notification.tasks.vouchers import TerminalState, cancel_pending
from tests.notif_seed import CIPHER, KEY_REF, envelope, seed_email_route


@pytest.mark.asyncio
async def test_voucher_terminal_state_cancels_pending_and_late_send(
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
    base = envelope(tenant_a, company, subject, event_key="voucher.sales_order.issued")
    send = base.model_copy(
        update={
            "payload": base.payload
            | {
                "source_service": "vouchers",
                "aggregate_type": "voucher",
                "subject_type": "party_general",
                "aggregate_id": str(voucher),
                "source_version": 3,
            },
        }
    )
    result = await handle_send_command(session, send, cipher=CIPHER, key_ref=KEY_REF)
    assert result.deliveries_created == 1
    state = TerminalState(
        company_id=company,
        voucher_id=voucher,
        source_version=4,
        status="CANCELLED",
    )
    await cancel_pending(session, base, state)
    await session.commit()
    with tenant_scope(tenant_a):
        current = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.request_id == result.request_id,
            )
        )
        assert current is not None and current.status == "cancelled"
        stored = await session.scalar(
            select(VoucherSendState).where(
                VoucherSendState.company_id == company,
                VoucherSendState.voucher_id == voucher,
            )
        )
        assert stored is not None and stored.source_version == 4
    later = send.model_copy(update={"message_id": uuid7()})
    late = await handle_send_command(session, later, cipher=CIPHER, key_ref=KEY_REF)
    await cancel_pending(session, later, state)
    await session.commit()
    with tenant_scope(tenant_a):
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.request_id == late.request_id,
            )
        )
        assert delivery is not None and delivery.status == "cancelled"
