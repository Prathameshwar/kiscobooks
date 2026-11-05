from __future__ import annotations

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.models import NotificationDelivery, NotificationSpace
from notification.providers import SendCommand, SendResult
from notification.tasks.consume import handle_send_command
from notification.tasks.dispatch import Dispatcher
from tests.notif_seed import CIPHER, KEY_REF, envelope, seed_email_route


@pytest.mark.asyncio
async def test_capacity_wait_does_not_consume_an_attempt(
    session: AsyncSession, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant_a, company=company, subject=subject)
    with tenant_scope(tenant_a):
        session.add(NotificationSpace(id=tenant_a, tenant_id=tenant_a, kind="tenant"))
        for _ in range(2):
            await handle_send_command(
                session, envelope(tenant_a, company, subject), cipher=CIPHER, key_ref=KEY_REF
            )
        await session.commit()
        rows = list(
            await session.scalars(select(NotificationDelivery).order_by(NotificationDelivery.id))
        )
    sent = []

    class Provider:
        async def send(self, command: SendCommand) -> SendResult:
            sent.append(command)
            return SendResult("accepted", "native-message")

    dispatcher = Dispatcher(
        factory, {rows[0].provider_account_id: Provider()}, per_provider_minute=1
    )
    await dispatcher.dispatch(
        tenant_a, rows[0].id, SendCommand("destination", "sender", "body", None, "attempt1")
    )
    result = await dispatcher.dispatch(
        tenant_a, rows[1].id, SendCommand("destination", "sender", "body", None, "attempt2")
    )
    assert result.error_code == "local_capacity_limit" and len(sent) == 1
    assert sent[0].attempt_key == f"{rows[0].id}:1"
    with tenant_scope(tenant_a):
        row = await session.get(NotificationDelivery, rows[1].id, populate_existing=True)
        assert row is not None and row.attempt_count == 0 and row.status == "pending"
        assert row.next_attempt_at is not None and row.next_attempt_at > utcnow()


@pytest.mark.parametrize(
    "gate", ["schedule", "backoff", "request_expiry", "content_expiry", "purged", "destination"]
)
async def test_claim_rechecks_time_and_content_before_network(session, factory, tenant_a, gate):
    import datetime as dt

    from billing_platform.errors import ConflictError

    from notification.models import (
        DeliveryAttempt,
        NotificationContent,
        NotificationRequest,
        RecipientEndpoint,
    )
    from tests.test_normalize import _make_sent_delivery

    delivery = await _make_sent_delivery(session, tenant_a, status="pending")
    with tenant_scope(tenant_a):
        request = await session.get(NotificationRequest, delivery.request_id)
        content = await session.get(NotificationContent, delivery.id)
        now = utcnow()
        if gate == "schedule":
            request.scheduled_at = now + dt.timedelta(minutes=5)
        elif gate == "backoff":
            delivery.next_attempt_at = now + dt.timedelta(minutes=5)
        elif gate == "request_expiry":
            request.expires_at = now - dt.timedelta(seconds=1)
        elif gate == "content_expiry":
            content.expires_at = now - dt.timedelta(seconds=1)
        elif gate == "destination":
            endpoint = await session.get(RecipientEndpoint, delivery.recipient_endpoint_id)
            endpoint.destination_hmac = b"z" * 32
        else:
            content.purged_at = now
        await session.commit()

    class Provider:
        async def send(self, command):
            pytest.fail("claim must not reach provider IO")

    dispatcher = Dispatcher(factory, {delivery.provider_account_id: Provider()})
    command = SendCommand("destination", "sender", "body", None, "stale-prepared-key")
    if gate in {"schedule", "backoff"}:
        with pytest.raises(ConflictError, match="not due"):
            await dispatcher.dispatch(tenant_a, delivery.id, command)
    else:
        result = await dispatcher.dispatch(tenant_a, delivery.id, command)
        assert result.outcome == "permanent_failure"
    with tenant_scope(tenant_a):
        assert list(await session.scalars(select(DeliveryAttempt))) == []
        row = await session.get(NotificationDelivery, delivery.id, populate_existing=True)
        assert row.attempt_count == 0
        assert row.status == (
            "pending"
            if gate in {"schedule", "backoff"}
            else "failed"
            if gate in {"purged", "destination"}
            else "expired"
        )


async def test_changed_provider_snapshot_rebuilds_transport_without_sending(
    session, factory, tenant_a
):
    import datetime as dt

    from billing_platform.errors import ConflictError

    from notification.models import DeliveryAttempt, ProviderAccount
    from tests.test_normalize import _make_sent_delivery

    delivery = await _make_sent_delivery(session, tenant_a, status="pending")
    with tenant_scope(tenant_a):
        provider = await session.get(ProviderAccount, delivery.provider_account_id)
        old_revision = provider.updated_at
        provider.updated_at += dt.timedelta(seconds=1)
        await session.commit()

    class Provider:
        async def send(self, command):
            pytest.fail("credentials from an obsolete configuration cannot send")

    dispatcher = Dispatcher(
        factory, {provider.id: Provider()}, provider_revisions={provider.id: old_revision}
    )
    with pytest.raises(ConflictError, match="rebuild"):
        await dispatcher.dispatch(
            tenant_a, delivery.id, SendCommand("dest", "sender", "body", None, "prepared")
        )
    with tenant_scope(tenant_a):
        current = await session.get(NotificationDelivery, delivery.id, populate_existing=True)
        assert current.status == "pending" and current.attempt_count == 0
        assert list(await session.scalars(select(DeliveryAttempt))) == []
