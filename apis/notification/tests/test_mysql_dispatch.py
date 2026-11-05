"""Native row-lock claiming and bounded dispatch admission."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from billing_platform.db import create_engine, tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import func, select, text

from notification.models import (
    DeliveryAttempt,
    NotificationDelivery,
    NotificationSpace,
    ProviderEvent,
)
from notification.ownership import session_factory
from notification.providers import SendCommand, SendResult
from notification.tasks.consume import handle_send_command
from notification.tasks.dispatch import Dispatcher
from notification.tasks.normalize import normalize_pending
from tests.notif_seed import CIPHER, KEY_REF, envelope, seed_email_route

pytestmark = pytest.mark.mysql


async def test_mysql_dispatch_claim_and_capacity_are_serialized(mysql_url: str) -> None:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "dbs/notification/alembic.ini"))
    config.set_main_option("script_location", str(root / "dbs/notification"))
    config.attributes["database_url"] = mysql_url
    await asyncio.to_thread(command.upgrade, config, "head")
    engine = create_engine(mysql_url)
    factory = session_factory(engine)
    tenant, company, subject = uuid7(), uuid7(), uuid7()
    sent = []

    class Provider:
        async def send(self, message: SendCommand) -> SendResult:
            sent.append(message)
            return SendResult("accepted", "native-claim-message")

    try:
        with tenant_scope(tenant):
            async with factory() as db:
                await seed_email_route(db, tenant=tenant, company=company, subject=subject)
                db.add(NotificationSpace(id=tenant, tenant_id=tenant, kind="tenant"))
                for _ in range(2):
                    await handle_send_command(
                        db, envelope(tenant, company, subject), cipher=CIPHER, key_ref=KEY_REF
                    )
                await db.commit()
                rows = list(
                    await db.scalars(select(NotificationDelivery).order_by(NotificationDelivery.id))
                )
        dispatcher = Dispatcher(
            factory, {rows[0].provider_account_id: Provider()}, per_provider_minute=1
        )

        async def send(row):
            return await dispatcher.dispatch(
                tenant, row.id, SendCommand("destination", "sender", "body", None, str(row.id))
            )

        results = await asyncio.gather(*(send(row) for row in rows))
        assert sorted(result.outcome for result in results) == ["accepted", "retryable_failure"]
        assert len(sent) == 1
        with tenant_scope(tenant):
            async with factory() as db:
                assert await db.scalar(select(func.count(DeliveryAttempt.id))) == 1
                accepted = (
                    await db.scalars(
                        select(NotificationDelivery).where(
                            NotificationDelivery.status == "accepted"
                        )
                    )
                ).one()
        with pytest.raises(ConflictError):
            await send(accepted)
        assert len(sent) == 1
        waiting = next(row for row in rows if row.id != accepted.id)
        with tenant_scope(tenant):
            async with factory() as db:
                due = await db.get(NotificationDelivery, waiting.id, with_for_update=True)
                assert due is not None
                due.next_attempt_at = utcnow()
                await db.commit()

        class ReceiptBeforeResponse:
            async def send(self, message: SendCommand) -> SendResult:
                with tenant_scope(tenant):
                    async with factory() as db:
                        db.add(
                            ProviderEvent(
                                tenant_id=tenant,
                                provider_account_id=waiting.provider_account_id,
                                external_event_key="native-recovery",
                                attempt_key=message.attempt_key,
                                provider_message_id="native-recovered",
                                event_type="Delivery",
                                signature_verified=True,
                                received_at=utcnow(),
                                payload_sha256=b"x" * 32,
                                encryption_key_ref=KEY_REF,
                                processing_status="pending",
                            )
                        )
                        await db.commit()
                async with factory() as db:
                    assert await normalize_pending(db) == 1
                    await db.commit()
                return SendResult("unknown", None, error_code="ambiguous_transport")

        recovery = Dispatcher(factory, {waiting.provider_account_id: ReceiptBeforeResponse()})
        await recovery.dispatch(
            tenant,
            waiting.id,
            SendCommand("destination", "sender", "body", None, f"{waiting.id}:1"),
        )
        with tenant_scope(tenant):
            async with factory() as db:
                recovered = await db.get(NotificationDelivery, waiting.id)
                assert recovered is not None and recovered.status == "delivered"
                assert (
                    recovered.provider_message_id == "native-recovered"
                    and recovered.attempt_count == 1
                )
        # Real optimizer inspection for the high-volume owner/date keyset read.
        async with engine.connect() as conn:
            plan = (
                (
                    await conn.execute(
                        text(
                            "EXPLAIN FORMAT=TRADITIONAL SELECT id FROM notification_delivery "
                            "WHERE tenant_id=UNHEX(:tenant) AND space_id=UNHEX(:space) "
                            "ORDER BY created_at DESC,id DESC LIMIT 51"
                        ),
                        {"tenant": tenant.hex, "space": tenant.hex},
                    )
                )
                .mappings()
                .one()
            )
            assert "ix_notification_delivery_scoped_list_1" in (plan["possible_keys"] or "")
    finally:
        await engine.dispose()
