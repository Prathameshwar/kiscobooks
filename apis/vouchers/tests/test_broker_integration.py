import os
import secrets
import uuid
from pathlib import Path

import aio_pika
import pytest
from billing_platform.broker import BrokerSource, ConfirmedPublisher, authenticated_envelope
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.delivery import publish_batch
from billing_platform.service_auth import ServiceKey
from conftest import TENANT
from sqlalchemy import func, select
from test_foundation import create_type, draft

from vouchers.events.audit_contract import AUDIT_EVENTS


@pytest.mark.rabbitmq
async def test_confirmed_outbox_delivery_to_real_broker_and_audit_redelivery(
    client, prefix, app, monkeypatch
):
    url = os.environ.get("VOUCHERS_TEST_BROKER_URL")
    if not url:
        pytest.skip("set loopback VOUCHERS_TEST_BROKER_URL for native broker verification")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "audit/src"))
    from audit.domain.source_contract import validate_source
    from audit.metadata import service_metadata
    from audit.models import AuditEvent
    from audit.tasks.consume import handle_event

    kind = await create_type(client, prefix)
    await draft(client, prefix, kind["revision_id"])
    connection = await aio_pika.connect_robust(url, timeout=10)
    database = create_engine("sqlite+aiosqlite:///:memory:")
    factory = create_session_factory(database, guarded=True)
    try:
        async with database.begin() as db:
            await db.run_sync(service_metadata().create_all)
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        exchange = await channel.declare_exchange(
            "voucher_test_" + uuid.uuid4().hex, aio_pika.ExchangeType.TOPIC, auto_delete=True
        )
        queue = await channel.declare_queue(exclusive=True, auto_delete=True)
        await queue.bind(exchange, routing_key="vouchers.#")
        user = connection.url.user
        key = ServiceKey("vouchers", "audit", AUDIT_EVENTS, secrets.token_bytes(32))
        publisher = ConfirmedPublisher(exchange, key_id="vouchers.test", key=key, broker_user=user)
        result = await publish_batch(app.state.session_factory, publisher, event_types=AUDIT_EVENTS)
        assert result.confirmed == 2
        for _ in range(2):
            message = await queue.get(timeout=5)
            envelope = authenticated_envelope(
                message, sources={"vouchers.test": BrokerSource(key, user)}, audience="audit"
            )
            validate_source(envelope, "vouchers")
            with tenant_scope(TENANT):
                async with factory() as db, db.begin():
                    first = await handle_event(db, envelope, consumer_name="vouchers.audit.test")
                    duplicate = await handle_event(
                        db, envelope, consumer_name="vouchers.audit.test"
                    )
                    assert first.event_id is not None
                    assert duplicate.deduplicated
            await message.ack()
        with tenant_scope(TENANT):
            async with factory() as db:
                assert await db.scalar(select(func.count(AuditEvent.id))) == 2
        await exchange.delete(if_unused=False)
    finally:
        await connection.close()
        await database.dispose()
