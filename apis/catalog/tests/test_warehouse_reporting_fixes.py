"""Dated warehouse grouping and live stock definition fences stay consistent."""

import datetime as dt

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7

from catalog.models.stock_source import StockSourceFence
from catalog.models.warehouse_groups import (
    WarehouseGroup,
    WarehouseGroupAssignment,
    WarehouseGroupParent,
)
from catalog.models.warehouses import Warehouse
from catalog.tasks.stock_report_sources import masters
from tests.test_stock_source_fences import prepared


async def test_warehouse_group_snapshot_preserves_effective_membership(factory, tenant_a):
    company, _, fence = await prepared(factory, tenant_a)
    warehouse, parent, child = uuid7(), uuid7(), uuid7()
    day = utcnow().date()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            (await db.get(StockSourceFence, fence)).closed_at = utcnow()
        async with factory.begin() as db:
            db.add_all(
                [
                    Warehouse(
                        id=warehouse,
                        tenant_id=tenant_a,
                        company_id=company,
                        code="STORE",
                        name="Store",
                        kind="STORE",
                        is_system=False,
                        is_active=True,
                    ),
                    WarehouseGroup(
                        id=parent,
                        tenant_id=tenant_a,
                        company_id=company,
                        code="PARENT",
                        name="Region",
                    ),
                    WarehouseGroup(
                        id=child, tenant_id=tenant_a, company_id=company, code="CHILD", name="Area"
                    ),
                ]
            )
        async with factory.begin() as db:
            db.add_all(
                [
                    WarehouseGroupParent(
                        tenant_id=tenant_a,
                        company_id=company,
                        group_id=child,
                        parent_group_id=parent,
                        valid_from=day - dt.timedelta(days=10),
                    ),
                    WarehouseGroupAssignment(
                        tenant_id=tenant_a,
                        company_id=company,
                        warehouse_id=warehouse,
                        group_id=parent,
                        valid_from=day - dt.timedelta(days=10),
                        valid_to=day - dt.timedelta(days=1),
                    ),
                    WarehouseGroupAssignment(
                        tenant_id=tenant_a,
                        company_id=company,
                        warehouse_id=warehouse,
                        group_id=child,
                        valid_from=day,
                    ),
                ]
            )
        async with factory() as db:
            previous = {
                row["location_id"]: row
                for row in await masters(db, company, day - dt.timedelta(days=1))
                if row["kind"] == "LOCATION"
            }
            current = {
                row["location_id"]: row
                for row in await masters(db, company, day)
                if row["kind"] == "LOCATION"
            }
            assert previous[str(warehouse)]["parent_id"] == str(parent)
            assert current[str(warehouse)]["parent_id"] == str(child)
            assert current[str(child)]["parent_id"] == str(parent)
            assert current[str(parent)]["is_group"] is True
            assert current[str(warehouse)]["sale_eligible"] is False
        async with factory.begin() as db:
            db.add(
                StockSourceFence(
                    id=uuid7(),
                    tenant_id=tenant_a,
                    company_id=company,
                    execution_id=uuid7(),
                    actor_user_id=uuid7(),
                    request_hash="a" * 64,
                    expires_at=utcnow() + dt.timedelta(seconds=60),
                    facts={},
                )
            )
        with pytest.raises(ConflictError, match="stock posting"):
            async with factory.begin() as db:
                (await db.get(WarehouseGroup, parent)).name = "Changed during stock execution"
