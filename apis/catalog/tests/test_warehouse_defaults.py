"""Verified inventory enrollment provides usable definitions without rewriting user policy."""

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import PlatformError
from billing_platform.ids import uuid7
from sqlalchemy import select

from catalog.models import Outbox
from catalog.models.classification import CatalogPolicyState
from catalog.models.warehouses import (
    CompanyWarehouseConfiguration,
    Warehouse,
    WarehouseOperationPolicyRevision,
)
from catalog.tasks.warehouse_defaults import ensure_warehouse_defaults
from catalog.tasks.warehouse_operations import flag_values
from tests.test_unit_defaults import provision


async def test_inventory_enrollment_provisions_main_transit_policies_once(factory, tenant_a):
    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            result = await ensure_warehouse_defaults(db, company)
            assert result.status == "READY" and result.created_records == 5
        async with factory.begin() as db:
            configuration = await db.scalar(select(CompanyWarehouseConfiguration))
            locations = {row.code: row for row in await db.scalars(select(Warehouse))}
            assert set(locations) == {"MAIN", "TRANSIT"}
            assert configuration.main_warehouse_id == locations["MAIN"].id
            assert configuration.transit_warehouse_id == locations["TRANSIT"].id
            assert locations["MAIN"].timezone == "Asia/Kolkata"
            assert locations["TRANSIT"].timezone is None
            assert all(row.is_system and row.is_active for row in locations.values())
            policy = {
                row.warehouse_id: row
                for row in await db.scalars(select(WarehouseOperationPolicyRevision))
            }
            assert all(flag_values(policy[locations["MAIN"].id]).values())
            transit = policy[locations["TRANSIT"].id]
            assert (
                transit.allow_transfer_in
                and transit.allow_transfer_out
                and not transit.allow_sale_issue
            )
            state = await db.scalar(select(CatalogPolicyState))
            generation = state.generation
            repeat = await ensure_warehouse_defaults(db, company)
            assert repeat.created_records == 0 and state.generation == generation
            events = list(
                await db.scalars(
                    select(Outbox).where(
                        Outbox.aggregate_type.in_(
                            (
                                "catalog.warehouse",
                                "catalog.company_warehouse_configuration",
                                "catalog.warehouse_operation_policy_revision",
                            )
                        )
                    )
                )
            )
            assert len(events) == 5
            assert all(row.payload["actor_type"] == "system" for row in events)
        # A later company policy is retained; enrollment never re-enables sales.
        async with factory.begin() as db:
            current = await db.scalar(
                select(WarehouseOperationPolicyRevision).where(
                    WarehouseOperationPolicyRevision.warehouse_id == locations["MAIN"].id,
                    WarehouseOperationPolicyRevision.effective_to.is_(None),
                )
            )
            now = utcnow()
            current.effective_to = now
            db.add(
                WarehouseOperationPolicyRevision(
                    id=uuid7(),
                    tenant_id=tenant_a,
                    company_id=company,
                    row_version=1,
                    warehouse_id=current.warehouse_id,
                    revision=2,
                    effective_from=now,
                    effective_to=None,
                    **(flag_values(current) | {"allow_sale_issue": False}),
                )
            )
        async with factory.begin() as db:
            assert (await ensure_warehouse_defaults(db, company)).created_records == 0
            current = await db.scalar(
                select(WarehouseOperationPolicyRevision).where(
                    WarehouseOperationPolicyRevision.warehouse_id == locations["MAIN"].id,
                    WarehouseOperationPolicyRevision.effective_to.is_(None),
                )
            )
            assert current.allow_sale_issue is False and current.revision == 2


async def test_inventory_enabled_after_creation_gets_defaults_and_tenant_scope_holds(
    factory, tenant_a, tenant_b
):
    company = uuid7()
    await provision(factory, tenant_a, company, inventory=False)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert (await ensure_warehouse_defaults(db, company)).status == "READY"
            assert {row.code for row in await db.scalars(select(Warehouse))} == {"MAIN", "TRANSIT"}
    await provision(factory, tenant_a, company, inventory=True, version=3)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert (await ensure_warehouse_defaults(db, company)).created_records == 0
    with tenant_scope(tenant_b):
        async with factory.begin() as db:
            assert list(await db.scalars(select(Warehouse))) == []
            with pytest.raises(PlatformError):
                await ensure_warehouse_defaults(db, company)
