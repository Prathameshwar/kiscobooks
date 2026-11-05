"""Scheduled maintenance jobs, tested on SQLite (docs/notification-operations.md)."""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import NotificationContent, NotificationDelivery, ProviderEvent
from notification.tasks.consume import handle_send_command
from notification.tasks.maintenance import (
    detect_stuck_deliveries,
    due_retry_deliveries,
    expire_purged_deliveries,
    purge_expired_content,
    reconcile_unmatched,
)
from notification.tasks.scheduler import run_maintenance_once
from tests.notif_seed import CIPHER, KEY_REF, NOW, envelope, seed_email_route

pytestmark = pytest.mark.asyncio


async def _delivery(session: AsyncSession, tenant: uuid.UUID) -> NotificationDelivery:
    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant, company=company, subject=subject)
    result = await handle_send_command(
        session, envelope(tenant, company, subject), cipher=CIPHER, key_ref=KEY_REF
    )
    await session.commit()
    with tenant_scope(tenant):
        return (
            await session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.request_id == result.request_id
                )
            )
        ).one()


async def test_purge_expired_content_nulls_ciphertext_keeps_hash(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    delivery = await _delivery(session, tenant_a)
    with tenant_scope(tenant_a):
        content = await session.get(NotificationContent, delivery.id)
        assert content is not None
        original_hash = content.content_sha256
        content.expires_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)  # already expired
        await session.commit()

    purged = await purge_expired_content(session)
    await session.commit()
    assert purged >= 1
    with tenant_scope(tenant_a):
        after = await session.get(NotificationContent, delivery.id)
    assert after is not None
    assert after.body_text_ciphertext is None
    assert after.purged_at is not None
    assert after.content_sha256 == original_hash  # evidence kept


async def test_detect_stuck_deliveries_hold_ambiguous_send(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    delivery = await _delivery(session, tenant_a)
    with tenant_scope(tenant_a):
        row = await session.get(NotificationDelivery, delivery.id)
        assert row is not None
        row.status = "sending"
        row.updated_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
        await session.commit()

    reset = await detect_stuck_deliveries(session)
    await session.commit()
    assert reset == 1
    with tenant_scope(tenant_a):
        after = await session.get(NotificationDelivery, delivery.id)
    assert after is not None
    assert after.status == "sending"
    assert after.status_reason == "ambiguous_stuck_send"


async def test_due_retry_deliveries_lists_elapsed(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    delivery = await _delivery(session, tenant_a)
    with tenant_scope(tenant_a):
        row = await session.get(NotificationDelivery, delivery.id)
        assert row is not None
        row.status = "retry_wait"
        row.next_attempt_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
        await session.commit()

    due = await due_retry_deliveries(session, now=NOW)
    assert delivery.id in due


async def test_reconcile_unmatched_requeues_when_delivery_appears(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    delivery = await _delivery(session, tenant_a)
    with tenant_scope(tenant_a):
        row = await session.get(NotificationDelivery, delivery.id)
        assert row is not None
        row.provider_message_id = "PMID-late"
        await session.commit()
        session.add(
            ProviderEvent(
                id=uuid7(),
                tenant_id=tenant_a,
                provider_account_id=delivery.provider_account_id,
                external_event_key="ext-late",
                provider_message_id="PMID-late",
                event_type="Delivery",
                signature_verified=True,
                received_at=NOW,
                payload_ciphertext=None,
                payload_sha256=b"0" * 32,
                encryption_key_ref=KEY_REF,
                processing_status="unmatched",
            )
        )
        await session.commit()

    requeued = await reconcile_unmatched(session)
    await session.commit()
    assert requeued == 1
    with tenant_scope(tenant_a):
        event = (
            await session.scalars(
                select(ProviderEvent).where(ProviderEvent.external_event_key == "ext-late")
            )
        ).one()
    assert event.processing_status == "pending"


async def test_run_maintenance_once_normalizes_a_pending_event(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    delivery = await _delivery(session, tenant_a)
    with tenant_scope(tenant_a):
        row = await session.get(NotificationDelivery, delivery.id)
        assert row is not None
        row.status = "accepted"
        row.provider_message_id = "PMID-sched"
        await session.commit()
        session.add(
            ProviderEvent(
                id=uuid7(),
                tenant_id=tenant_a,
                provider_account_id=delivery.provider_account_id,
                external_event_key="ext-sched",
                provider_message_id="PMID-sched",
                event_type="Delivery",
                signature_verified=True,
                received_at=NOW,
                payload_ciphertext=None,
                payload_sha256=b"0" * 32,
                encryption_key_ref=KEY_REF,
                processing_status="pending",
            )
        )
        await session.commit()

    summary = await run_maintenance_once(session)
    await session.commit()
    assert summary.normalized == 1
    with tenant_scope(tenant_a):
        refreshed = await session.get(NotificationDelivery, delivery.id)
    assert refreshed is not None
    assert refreshed.status == "delivered"


async def test_expire_purged_deliveries_transitions_expired_content(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    delivery = await _delivery(session, tenant_a)
    with tenant_scope(tenant_a):
        content = await session.get(NotificationContent, delivery.id)
        assert content is not None
        content.expires_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)  # already expired
        await session.commit()

    expired_count = await expire_purged_deliveries(session)
    await session.commit()
    assert expired_count == 1
    with tenant_scope(tenant_a):
        refreshed = await session.get(NotificationDelivery, delivery.id)
    assert refreshed is not None
    assert refreshed.status == "expired"
    assert refreshed.status_reason == "content_expired"


async def test_scheduler_pass_runs_all_maintenance_lanes(session: AsyncSession) -> None:
    from notification.tasks.scheduler import run_maintenance_once

    summary = await run_maintenance_once(session)
    assert summary.normalized == 0
    assert summary.stuck_flagged == 0
    assert summary.expired == 0


async def test_scheduler_recovers_after_a_failed_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    from notification.tasks import scheduler

    db = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=db)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    passes = AsyncMock(side_effect=[RuntimeError("transient database failure"), None])
    monkeypatch.setattr(scheduler, "run_maintenance_once", passes)
    monkeypatch.setattr(
        scheduler.asyncio, "sleep", AsyncMock(side_effect=[None, asyncio.CancelledError()])
    )
    settings = SimpleNamespace(stuck_sending_seconds=900)
    with pytest.raises(asyncio.CancelledError):
        await scheduler.run_scheduler(settings, factory, interval_seconds=1)
    assert passes.await_count == 2
    db.rollback.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.parametrize("status", ["sending", "accepted", "delivered", "read"])
async def test_retention_preserves_provider_outcomes(
    session: AsyncSession, tenant_a: uuid.UUID, status: str
) -> None:
    delivery = await _delivery(session, tenant_a)
    with tenant_scope(tenant_a):
        delivery.status = status
        content = await session.get(NotificationContent, delivery.id)
        assert content is not None
        content.expires_at = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
        await session.commit()
    await purge_expired_content(session)
    assert await expire_purged_deliveries(session) == 0
    assert delivery.status == status
