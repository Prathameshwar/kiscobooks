from __future__ import annotations

import uuid
from contextvars import ContextVar

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.base import Base
from billing_platform.db.mixins import IdMixin, TenantMixin
from billing_platform.db.partition import PartitionedSession, install_partition_guard
from billing_platform.db.tenant_context import TenantContextError
from billing_platform.db.types import Uuid7
from billing_platform.ids import uuid7

active_partition: ContextVar[uuid.UUID | None] = ContextVar("test_partition", default=None)


class PartitionMixin:
    partition_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class PartitionRecord(PartitionMixin, IdMixin, TenantMixin, Base):
    __tablename__ = "test_partition_record"
    label: Mapped[str] = mapped_column(default="original")


install_partition_guard(PartitionMixin, column="partition_id", resolve=active_partition.get)


@pytest.mark.asyncio
async def test_partition_query_cache_identity_map_and_write_guards(engine: AsyncEngine) -> None:
    owner, first, second = uuid7(), uuid7(), uuid7()
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        sync_session_class=PartitionedSession,
        expire_on_commit=False,
        autoflush=False,
    )
    with tenant_scope(owner):
        async with factory() as db:
            with unfiltered():
                a = PartitionRecord(tenant_id=owner, partition_id=first)
                b = PartitionRecord(tenant_id=owner, partition_id=second)
                db.add_all([a, b])
                await db.commit()
            token = active_partition.set(first)
            try:
                assert [r.id for r in await db.scalars(select(PartitionRecord))] == [a.id]
                assert await db.get(PartitionRecord, b.id) is None
                a.label = "pending change"
                assert (await db.get(PartitionRecord, a.id)).label == "pending change"
                await db.flush()
                await db.commit()
                # A clean cached row still refreshes, including lock-taking reads.
                async with factory() as other:
                    refreshed = await other.get(PartitionRecord, a.id)
                    refreshed.label = "remote change"
                    await other.commit()
                assert (
                    await db.get(PartitionRecord, a.id, with_for_update=True)
                ).label == "remote change"
                bad = PartitionRecord(tenant_id=owner, partition_id=second)
                db.add(bad)
                with pytest.raises(TenantContextError, match="outside"):
                    await db.flush()
                await db.rollback()
            finally:
                active_partition.reset(token)
        async with factory() as db:
            with pytest.raises(TenantContextError, match="context"):
                await db.scalars(select(PartitionRecord))
            token = active_partition.set(second)
            try:
                assert len(list(await db.scalars(select(PartitionRecord)))) == 1
                active_partition.set(first)
                with pytest.raises(TenantContextError, match="change partition"):
                    await db.scalars(select(PartitionRecord))
            finally:
                active_partition.reset(token)
