"""Opt-in real RabbitMQ transport; the Audit database fixture is isolated SQLite."""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from pathlib import Path

import aio_pika
import pytest
from billing_platform.broker import (
    BrokerSource,
    ConfirmedPublisher,
    confirmed_channel,
    declare_consumer_queue,
)
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.delivery import publish_batch
from billing_platform.outbox import audit_payload, emit
from billing_platform.service_auth import ServiceKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from audit.models import AuditEvent
from audit.tasks.consume import receive_audit


@pytest.mark.parametrize(
    "issuer,event_type,entity",
    [
        ("identity", "company.updated", "company"),
        ("identity", "platform.account_decision_completed", "account_review"),
        ("identity", "platform.accounts_read", "account_review"),
        ("identity", "platform.account_reconciled", "account_review"),
        ("catalog", "catalog.bulk_job.update", "catalog.bulk_job"),
        ("accounting", "accounting.party.update", "accounting.party"),
        ("notification", "notification.provider_account.updated", "notification.provider_account"),
        ("design", "design.invoice_template.update", "design.invoice_template"),
        ("vouchers", "vouchers.voucher.update", "vouchers.voucher"),
        ("reports", "reports.report.defined", "reports.report"),
        ("audit", "audit.exported", "audit_event"),
    ],
)
@pytest.mark.skipif(
    not os.environ.get("IDENTITY_TEST_BROKER_URL"), reason="explicit isolated RabbitMQ URL required"
)
async def test_live_confirm_unroutable_retry_redelivery_reconnect_and_dead_letter(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    issuer: str,
    event_type: str,
    entity: str,
) -> None:
    url = os.environ["IDENTITY_TEST_BROKER_URL"]
    user = os.environ["IDENTITY_TEST_BROKER_USER"]
    name = "identity-audit-test-" + uuid.uuid4().hex
    key = ServiceKey(issuer, "audit", frozenset({event_type}), os.urandom(32))
    sources = {"test": BrokerSource(key, user)}
    company = uuid.uuid4()
    async with factory() as db, db.begin():
        row = emit(
            db,
            tenant_id=tenant_a,
            aggregate_type=entity,
            aggregate_id=company,
            event_type=event_type,
            payload=audit_payload(
                action=event_type,
                category="admin",
                entity_type=entity,
                entity_id=company,
                actor_user_id=uuid.uuid4(),
                company_id=company,
                changes={"display_name": {"to": "[redacted]"}},
            ),
        )
        mid = row.message_id
    async with confirmed_channel(url) as channel:
        exchange = await channel.declare_exchange(name, aio_pika.ExchangeType.TOPIC, durable=True)
        publisher = ConfirmedPublisher(exchange, key_id="test", key=key, broker_user=user)
        # Broker rejects an unroutable mandatory message: the original outbox stays pending.
        failed = await publish_batch(factory, publisher, event_types=key.operations)
        assert failed.deferred == 1 and failed.confirmed == 0
        queue = await declare_consumer_queue(
            channel,
            exchange_name=name,
            queue_name=name,
            dead_letter_exchange=name + ".dlx",
            routes=(event_type,),
            single_active_consumer=True,
        )
        async with factory() as db, db.begin():
            pending = await db.scalar(select(Outbox).where(Outbox.message_id == mid))
            assert pending is not None and pending.published_at is None
            pending.available_at = utcnow()
        sent = await publish_batch(factory, publisher, event_types=key.operations)
        assert sent.confirmed == 1
        message = await queue.get(timeout=5)
        assert message is not None
        # A worker closes before committing/ACK. RabbitMQ must redeliver.
    if os.environ.get("IDENTITY_TEST_ALLOW_BROKER_RESTART") == "1":
        if "@127.0.0.1:5672/bill_identity_test" not in url:
            raise AssertionError("restart is restricted to the explicitly installed local node")
        script = Path(__file__).resolve().parents[3] / "start/win/rabbitmq-local.ps1"
        for action in ("stop", "start"):
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-Action",
                    action,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                timeout=60,
            )
            assert result.returncode == 0, "local RabbitMQ control command failed"
        for _attempt in range(60):
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", 5672)
                writer.close()
                await writer.wait_closed()
                break
            except OSError:
                await asyncio.sleep(0.5)
        else:
            raise AssertionError("local RabbitMQ did not recover")
    async with confirmed_channel(url) as channel:
        queue = await channel.get_queue(name)
        incoming = await queue.get(timeout=5)
        assert incoming is not None and incoming.redelivered
        await receive_audit(factory, incoming, sources=sources, consumer_name=name)
        exchange = await channel.get_exchange(name)
        # Re-deliver the same signed body with broker metadata: inbox prevents a second effect.
        await exchange.publish(
            aio_pika.Message(
                body=incoming.body,
                headers=dict(incoming.headers),
                content_type="application/json",
                user_id=user,
                message_id=str(mid),
                type=event_type,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            event_type,
        )
        duplicate = await queue.get(timeout=5)
        assert duplicate is not None
        await receive_audit(factory, duplicate, sources=sources, consumer_name=name)
        await exchange.publish(
            aio_pika.Message(
                body=b"{}",
                content_type="application/json",
                user_id=user,
                message_id=str(uuid.uuid4()),
                type=event_type,
            ),
            event_type,
        )
        invalid = await queue.get(timeout=5)
        assert invalid is not None
        await receive_audit(factory, invalid, sources=sources, consumer_name=name)
        dead = await channel.get_queue(name + ".dead")
        rejected = await dead.get(timeout=5)
        assert rejected is not None
        await rejected.ack()
        with tenant_scope(tenant_a):
            async with factory() as db:
                rows = list(await db.scalars(select(AuditEvent)))
                assert len(rows) == 1 and rows[0].company_id == company
                assert rows[0].changes == {"display_name": {"to": "[redacted]"}}
        await queue.delete(if_unused=False, if_empty=False)
        await dead.delete(if_unused=False, if_empty=False)
        await exchange.delete(if_unused=False)
        dlx = await channel.get_exchange(name + ".dlx")
        await dlx.delete(if_unused=False)
