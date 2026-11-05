"""Worker handler and retention invariants use a real SQL transaction."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.delivery import consume_once
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.service_auth import CompanyServiceScope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.projections import ProjectionCheckpoint, SourceEventBuffer
from catalog.tasks.projections import activate_snapshot, buffer_change, prune_buffer
from catalog.tasks.source_worker import EVENT_TYPE, handle_change
from tests.source_factories import change, snapshot


async def test_worker_current_tenant_contract_dedupe_and_rollback(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company))
    event = MessageEnvelope(
        message_id=uuid7(),
        tenant_id=tenant_a,
        event_type=EVENT_TYPE,
        schema_version=1,
        occurred_at=utcnow(),
        payload=change(tenant_a, 3).model_dump(mode="json"),
    )

    async def handler(db: AsyncSession, incoming: MessageEnvelope) -> None:
        await handle_change(db, incoming, allowed_tenants=frozenset({tenant_a}))

    assert await consume_once(factory, event, handler, consumer_name="source.test")
    assert not await consume_once(factory, event, handler, consumer_name="source.test")
    with pytest.raises(ValidationFailedError, match="integrity"):
        await consume_once(
            factory,
            event.model_copy(update={"message_id": uuid7()}),
            handler,
            consumer_name="source.test",
        )

    for malformed in (
        event.model_copy(update={"tenant_id": uuid7(), "message_id": uuid7()}),
        event.model_copy(update={"event_type": "other.source", "message_id": uuid7()}),
        event.model_copy(update={"schema_version": 2, "message_id": uuid7()}),
        event.model_copy(
            update={"payload": change(uuid7(), 4).model_dump(mode="json"), "message_id": uuid7()}
        ),
    ):
        with pytest.raises(ValidationFailedError):
            await consume_once(factory, malformed, handler, consumer_name="source.test")
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert len(list(await db.scalars(select(SourceEventBuffer)))) == 1
            assert (await db.scalars(select(ProjectionCheckpoint))).one().source_version == 3


async def test_capture_retention_keeps_unmerged_changes(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            checkpoint = await activate_snapshot(db, snapshot(tenant_a, company))
            await buffer_change(db, message_id=uuid7(), change=change(tenant_a, 3))
            await buffer_change(db, message_id=uuid7(), change=change(tenant_a, 5))
            for row in await db.scalars(select(SourceEventBuffer)):
                row.received_at = utcnow() - dt.timedelta(minutes=6)
            await db.flush()
            assert await prune_buffer(db, [checkpoint]) == 1
            assert (await db.scalars(select(SourceEventBuffer))).one().source_version == 5
            # With no initialized company a future complete bootstrap supersedes
            # obsolete pre-bootstrap capture; no historical business data is purged.
            assert await prune_buffer(db, []) == 1


async def test_consumer_supervisor_cancels_refresh_and_reconnects_safely(
    monkeypatch: pytest.MonkeyPatch, engine: Any
) -> None:
    import asyncio
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    from pydantic import SecretStr

    from catalog.tasks import source_worker
    from catalog.tasks.source_worker import WorkerSettings
    from tests.test_identity_source_client import settings as source_settings

    attempts = 0
    renewals = 0
    received = []
    sleeps = []
    real_sleep = asyncio.sleep

    class Queue:
        @asynccontextmanager
        async def iterator(self) -> AsyncIterator[Any]:
            async def messages() -> AsyncIterator[object]:
                yield object()
                await asyncio.Event().wait()

            yield messages()

    @asynccontextmanager
    async def channel(url: str) -> AsyncIterator[object]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("unavailable broker")
        yield object()

    async def declare(*args: Any, **kwargs: Any) -> Queue:
        assert kwargs["routes"] == (EVENT_TYPE,)
        return Queue()

    async def receive(*args: Any, **kwargs: Any) -> None:
        received.append(kwargs["consumer_name"])
        assert kwargs["audience"] == "catalog"
        tenant = config.source_subscriptions[0].tenant_id
        event = MessageEnvelope(
            message_id=uuid7(),
            tenant_id=tenant,
            event_type=EVENT_TYPE,
            schema_version=1,
            occurred_at=utcnow(),
            payload=change(tenant, 2).model_dump(mode="json"),
        )
        with tenant_scope(tenant):
            async with args[0].begin() as db:
                await kwargs["handler"](db, event)

    async def refresh(*args: Any) -> None:
        nonlocal renewals
        renewals += 1
        if renewals == 2:
            raise RuntimeError("refresh process failed")

    async def pause(seconds: float) -> None:
        sleeps.append(seconds)
        if sleeps.count(5) == 2:
            raise asyncio.CancelledError
        await real_sleep(0)

    monkeypatch.setattr(source_worker, "create_engine", lambda url: engine)
    monkeypatch.setattr(source_worker, "confirmed_channel", channel)
    monkeypatch.setattr(source_worker, "declare_consumer_queue", declare)
    monkeypatch.setattr(source_worker, "receive_one", receive)
    monkeypatch.setattr(source_worker, "refresh_once", refresh)
    monkeypatch.setattr(asyncio, "sleep", pause)
    config = WorkerSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        identity_source=source_settings(),
        source_subscriptions=(CompanyServiceScope(tenant_id=uuid7(), company_id=uuid7()),),
        source_broker_url=SecretStr("amqp://ephemeral.invalid"),
        source_broker_user="identity",
        source_event_secret=SecretStr("ephemeral-event-key" * 3),
    )
    with pytest.raises(asyncio.CancelledError):
        await source_worker.run(config)
    assert attempts == 2 and renewals == 2
    assert received == ["catalog.identity_context.v1"]
