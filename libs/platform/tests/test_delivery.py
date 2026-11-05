from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.db.platform_models import Outbox, ProcessedMessage
from billing_platform.db.tenant_context import get_current_tenant
from billing_platform.db.types import utcnow
from billing_platform.delivery import OutgoingMessage, consume_once, publish_batch
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.outbox import emit


async def test_confirm_retry_preserves_message_identity_and_safe_errors(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    async with factory() as db, db.begin():
        row = emit(
            db,
            tenant_id=tenant_a,
            aggregate_id=uuid7(),
            aggregate_type="item",
            event_type="item.changed",
            payload={"amount": "1.0000"},
        )
        message_id = row.message_id
    sent: list[OutgoingMessage] = []

    async def publish(message: OutgoingMessage) -> bool:
        sent.append(message)
        if len(sent) == 1:
            raise RuntimeError("broker URL and credentials must not be retained")
        return True

    failed = await publish_batch(factory, publish)
    assert failed.confirmed == 0 and failed.deferred == 1
    assert (await publish_batch(factory, publish)).confirmed == 0
    async with factory() as db, db.begin():
        stored = (await db.scalars(select(Outbox))).one()
        assert stored.published_at is None and stored.last_error == "RuntimeError"
        stored.available_at = utcnow()
    assert (await publish_batch(factory, publish)).confirmed == 1
    assert len(sent) == 2 and sent[0] == sent[1] and sent[0].message_id == message_id
    assert MessageEnvelope.model_validate_json(sent[0].body).message_id == message_id
    assert (await publish_batch(factory, publish)).confirmed == 0


async def test_negative_confirmation_never_marks_published(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    async with factory() as db, db.begin():
        emit(
            db,
            tenant_id=tenant_a,
            aggregate_id=uuid7(),
            aggregate_type="item",
            event_type="item.changed",
            payload={},
        )

    async def no_confirmation(message: OutgoingMessage) -> bool:
        return False

    result = await publish_batch(factory, no_confirmation)
    assert result.confirmed == 0 and result.deferred == 1


async def test_consumer_redelivery_fanout_and_rollback(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    envelope = MessageEnvelope(
        message_id=uuid7(),
        tenant_id=tenant_a,
        event_type="item.changed",
        schema_version=1,
        occurred_at=utcnow(),
        payload={},
    )

    async def handler(db: AsyncSession, incoming: MessageEnvelope) -> None:
        assert get_current_tenant() == tenant_a
        emit(
            db,
            tenant_id=tenant_a,
            aggregate_id=uuid7(),
            aggregate_type="test",
            event_type="test.applied",
            payload={},
        )

    assert await consume_once(factory, envelope, handler, consumer_name="first")
    assert not await consume_once(factory, envelope, handler, consumer_name="first")
    assert await consume_once(factory, envelope, handler, consumer_name="second")

    async def fail(db: AsyncSession, incoming: MessageEnvelope) -> None:
        await handler(db, incoming)
        await db.flush()
        raise ValueError("domain rejection")

    with pytest.raises(ValueError):
        await consume_once(factory, envelope, fail, consumer_name="failed")
    async with factory() as db:
        assert len((await db.scalars(select(ProcessedMessage))).all()) == 2
        assert len((await db.scalars(select(Outbox))).all()) == 2
    assert await consume_once(factory, envelope, handler, consumer_name="failed")
    assert get_current_tenant() is None


async def test_worker_configuration_bounds(factory: async_sessionmaker[AsyncSession]) -> None:
    async def publish(message: OutgoingMessage) -> bool:
        return True

    async def handler(db: AsyncSession, incoming: MessageEnvelope) -> None:
        return None

    invalid_arguments: tuple[dict[str, Any], ...] = ({"limit": 0}, {"timeout_seconds": 0})
    for arguments in invalid_arguments:
        with pytest.raises(ValueError):
            await publish_batch(factory, publish, **arguments)
    envelope = MessageEnvelope(
        message_id=uuid7(),
        tenant_id=uuid7(),
        event_type="item.changed",
        schema_version=1,
        occurred_at=utcnow(),
        payload={},
    )
    with pytest.raises(ValueError):
        await consume_once(factory, envelope, handler, consumer_name="invalid source name")
    with pytest.raises(ValueError):
        await consume_once(
            factory,
            envelope.model_copy(update={"tenant_id": uuid.UUID(int=0)}),
            handler,
            consumer_name="valid",
        )


async def test_filtered_outbox_leaves_other_consumer_routes_untouched(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    async with factory.begin() as db:
        for event_type in ("audit.event", "identity.catalog_context.changed"):
            emit(
                db,
                tenant_id=tenant_a,
                aggregate_id=uuid7(),
                aggregate_type="test",
                event_type=event_type,
                payload={},
            )
    sent = []

    async def publish(message: OutgoingMessage) -> bool:
        sent.append(message.routing_key)
        return True

    result = await publish_batch(
        factory, publish, event_types=frozenset({"identity.catalog_context.changed"})
    )
    assert result.confirmed == 1 and sent == ["identity.catalog_context.changed"]
    async with factory.begin() as db:
        audit = (await db.scalars(select(Outbox).where(Outbox.event_type == "audit.event"))).one()
        assert audit.attempt_count == 0 and audit.published_at is None
    for invalid in (frozenset(), frozenset({"identity.*"}), frozenset(str(i) for i in range(101))):
        with pytest.raises(ValueError):
            await publish_batch(factory, publish, event_types=invalid)


@pytest.mark.parametrize("count", (105, 1024))
async def test_large_route_registry_keeps_delivery_batches_bounded_and_exact(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, count: int
) -> None:
    routes = frozenset(f"test.event{i}" for i in range(count))
    allowed = {"test.event0", f"test.event{count - 1}"}
    async with factory.begin() as db:
        for event_type in (*sorted(allowed), "unrelated.changed"):
            emit(
                db,
                tenant_id=tenant_a,
                aggregate_id=uuid7(),
                aggregate_type="test",
                event_type=event_type,
                payload={},
            )
    sent: list[str] = []

    async def publish(message: OutgoingMessage) -> bool:
        sent.append(message.routing_key)
        return True

    first = await publish_batch(factory, publish, event_types=routes, limit=1)
    assert first.confirmed == 1 and len(sent) == 1 and sent[0] in allowed
    second = await publish_batch(factory, publish, event_types=routes, limit=1)
    assert second.confirmed == 1 and set(sent) == allowed
    async with factory() as db:
        untouched = await db.scalar(select(Outbox).where(Outbox.event_type == "unrelated.changed"))
        assert (
            untouched is not None
            and untouched.published_at is None
            and untouched.attempt_count == 0
        )
    with pytest.raises(ValueError):
        await publish_batch(
            factory, publish, event_types=frozenset(f"test.event{i}" for i in range(1025))
        )
