import datetime as dt
import uuid

import pytest
from billing_platform.db import get_current_tenant, tenant_scope, unfiltered
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from fastapi import FastAPI, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.api.dependencies import session
from catalog.models import IdempotencyKey, Outbox


def record(tenant: uuid.UUID) -> IdempotencyKey:
    return IdempotencyKey(
        tenant_id=tenant,
        key_value="test",
        endpoint="/fixture",
        request_hash="0" * 64,
        state="in_progress",
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
    )


async def test_idempotency_storage_is_tenant_isolated(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    for tenant in (tenant_a, tenant_b):
        with tenant_scope(tenant):
            async with factory.begin() as db:
                db.add(record(tenant))
    for tenant in (tenant_a, tenant_b):
        with tenant_scope(tenant):
            async with factory() as db:
                rows = (await db.scalars(select(IdempotencyKey))).all()
                assert len(rows) == 1 and rows[0].tenant_id == tenant


@pytest.mark.parametrize("fail", [False, True])
async def test_request_transaction_commits_or_rolls_back_outbox_atomically(
    app: FastAPI,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    fail: bool,
) -> None:
    generator = session(Request({"type": "http", "app": app}), Actor(tenant_a, uuid7()))
    db = await anext(generator)
    assert get_current_tenant() == tenant_a
    db.add(record(tenant_a))
    emit(
        db,
        aggregate_type="fixture",
        aggregate_id=uuid7(),
        event_type="fixture.created",
        tenant_id=tenant_a,
        payload={"action": "fixture.created"},
    )
    await db.flush()
    if fail:
        with pytest.raises(RuntimeError, match="abort"):
            await generator.athrow(RuntimeError("abort"))
    else:
        with pytest.raises(StopAsyncIteration):
            await anext(generator)
    assert get_current_tenant() is None
    with unfiltered():
        async with factory() as check:
            assert len((await check.scalars(select(IdempotencyKey))).all()) == int(not fail)
            assert len((await check.scalars(select(Outbox))).all()) == int(not fail)
