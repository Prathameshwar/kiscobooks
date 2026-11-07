"""Definition leases retain evidence and block every ORM source mutation path."""

import datetime as dt

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select

from catalog.models.classification import CatalogPolicyState
from catalog.models.stock_source import StockSourceFence
from catalog.models.units import UnitOfMeasure


async def prepared(factory, tenant, *, purpose=None):
    company, user = uuid7(), uuid7()
    now = utcnow()
    unit_id, fence_id = uuid7(), uuid7()
    with tenant_scope(tenant):
        async with factory.begin() as db:
            db.add(CatalogPolicyState(tenant_id=tenant, company_id=company, generation=1))
            db.add(
                UnitOfMeasure(
                    id=unit_id,
                    tenant_id=tenant,
                    company_id=company,
                    code="COUNT",
                    symbol="No",
                    name="Count",
                    dimension="COUNT",
                    decimal_places=0,
                    quantity_increment=1,
                    row_version=1,
                    is_active=True,
                )
            )
        async with factory.begin() as db:
            db.add(
                StockSourceFence(
                    id=fence_id,
                    tenant_id=tenant,
                    company_id=company,
                    execution_id=uuid7(),
                    actor_user_id=user,
                    request_hash="a" * 64,
                    expires_at=now + dt.timedelta(seconds=60),
                    closed_at=None,
                    facts={"purpose": purpose} if purpose else {},
                    created_by=user,
                    updated_by=user,
                )
            )
    return company, unit_id, fence_id


async def test_live_fence_blocks_source_changes_until_owner_release(factory, tenant_a):
    company, unit_id, fence_id = await prepared(factory, tenant_a)
    with tenant_scope(tenant_a):
        with pytest.raises(ConflictError, match="stock posting"):
            async with factory.begin() as db:
                unit = await db.get(UnitOfMeasure, unit_id)
                unit.name = "Changed while effects are pending"
        with pytest.raises(ConflictError, match="stock posting"):
            async with factory.begin() as db:
                unit = await db.get(UnitOfMeasure, unit_id)
                await db.delete(unit)
        async with factory.begin() as db:
            fence = await db.get(StockSourceFence, fence_id)
            fence.closed_at = utcnow()
        async with factory.begin() as db:
            unit = await db.get(UnitOfMeasure, unit_id)
            unit.name = "Changed after release"
        async with factory() as db:
            unit = await db.get(UnitOfMeasure, unit_id)
            assert unit.name == "Changed after release"
            assert await db.scalar(select(StockSourceFence.id)) == fence_id


async def test_report_snapshot_fence_does_not_block_unrelated_master_edit(factory, tenant_a):
    company, unit_id, fence_id = await prepared(factory, tenant_a, purpose="REPORT")
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            unit = await db.get(UnitOfMeasure, unit_id)
            unit.name = "Changed after report captured its records"
        async with factory() as db:
            assert (await db.get(UnitOfMeasure, unit_id)).name == "Changed after report captured its records"


async def test_fence_history_cannot_be_changed_reopened_or_deleted(factory, tenant_a):
    _, _, fence_id = await prepared(factory, tenant_a)
    with tenant_scope(tenant_a):
        for field, value in (
            ("request_hash", "b" * 64),
            ("company_id", uuid7()),
            ("expires_at", utcnow() + dt.timedelta(hours=1)),
            ("facts", {"forged": True}),
        ):
            with pytest.raises(ConflictError, match="immutable"):
                async with factory.begin() as db:
                    fence = await db.get(StockSourceFence, fence_id)
                    setattr(fence, field, value)
        with pytest.raises(ConflictError, match="deleted"):
            async with factory.begin() as db:
                await db.delete(await db.get(StockSourceFence, fence_id))
        async with factory.begin() as db:
            fence = await db.get(StockSourceFence, fence_id)
            fence.closed_at = utcnow()
        with pytest.raises(ConflictError, match="immutable"):
            async with factory.begin() as db:
                fence = await db.get(StockSourceFence, fence_id)
                fence.closed_at = None


async def test_fence_scope_does_not_block_another_company_or_leak_to_another_tenant(
    factory, tenant_a, tenant_b
):
    _, unit_id, fence_id = await prepared(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                UnitOfMeasure(
                    tenant_id=tenant_a,
                    company_id=uuid7(),
                    code="OTHER",
                    symbol="No",
                    name="Other",
                    dimension="COUNT",
                    decimal_places=0,
                    quantity_increment=1,
                    row_version=1,
                    is_active=True,
                )
            )
    with tenant_scope(tenant_b):
        async with factory() as db:
            assert await db.get(StockSourceFence, fence_id) is None
            assert await db.get(UnitOfMeasure, unit_id) is None
