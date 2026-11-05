"""Scoped persisted edge states for fail-closed product integration tests."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from billing_platform.db import tenant_scope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@asynccontextmanager
async def changed(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    model: type[Any],
    key: uuid.UUID,
    **values: Any,
) -> AsyncIterator[None]:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            row = await db.get(model, key)
            assert row is not None
            before = {field: getattr(row, field) for field in values}
            for field, value in values.items():
                setattr(row, field, value)
    try:
        yield
    finally:
        with tenant_scope(tenant):
            async with factory.begin() as db:
                row = await db.get(model, key)
                assert row is not None
                for field, value in before.items():
                    setattr(row, field, value)
