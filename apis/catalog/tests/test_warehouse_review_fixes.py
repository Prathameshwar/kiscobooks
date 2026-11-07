"""Warehouse correctness regressions converted from the review reproductions."""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select

from catalog.models.warehouse_groups import WarehouseGroupAssignment
from catalog.models.warehouses import Warehouse
from catalog.tasks.warehouse_defaults import ensure_warehouse_defaults
from catalog.tasks.warehouse_policy import group_dependency
from tests.test_commercial_api import command_headers
from tests.test_unit_defaults import provision
from tests.test_warehouse_groups import GROUPING, assign, create_group, create_location
from tests.warehouse_factories import RETIRE, auth, retire


async def test_review_invalid_timezone_is_rejected(client, factory, tenant_a):
    company, user, unknown_registration = uuid7(), uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    with pytest.raises(ZoneInfoNotFoundError):
        ZoneInfo("Not/AZone")
    response = await client.post(
        f"/v1/companies/{company}/warehouses",
        headers=command_headers(current),
        json={
            "code": "BAD_FACTS",
            "name": "Warehouse",
            "kind": "STORE",
            "timezone": "Not/AZone",
            "tax_registration_id": str(unknown_registration),
        },
    )
    assert response.status_code == 422, response.text
    assert "timezone" in response.text


async def test_inventory_off_enrollment_provisions_main(factory, tenant_a):
    company = uuid7()
    await provision(factory, tenant_a, company, inventory=False)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            result = await ensure_warehouse_defaults(db, company)
            assert result.status == "READY"
            assert await db.scalar(select(Warehouse.id).where(Warehouse.company_id == company))


async def test_single_location_create_metadata_is_read_only(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, features=("inventory",))
    root = f"/v1/companies/{company}"
    response = await client.get(
        root + "/entities/catalog.warehouse/field-set?operation=create", headers=current
    )
    assert response.status_code == 200, response.text
    fields = {row["key"]: row for row in response.json()["fields"]}
    assert all(not fields[key]["writable"] for key in ("code", "name", "kind"))
    rejected = await client.post(
        root + "/warehouses",
        headers=command_headers(current),
        json={
            "code": "EXTRA",
            "name": "Extra warehouse",
            "kind": "STORE",
        },
    )
    assert rejected.status_code == 409, rejected.text
    assert "multiple-godown" in rejected.text


async def test_empty_location_retirement_requires_reviewed_release(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, permission=RETIRE)
    root = f"/v1/companies/{company}/warehouses"
    created = await client.post(
        root,
        headers=command_headers(current),
        json={
            "code": "EMPTY",
            "name": "Empty warehouse",
            "kind": "STORE",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_active"] is True
    rejected = await client.post(
        root + "/" + created.json()["id"] + "/deactivate",
        headers=command_headers(current),
        json={
            "expected_version": created.json()["row_version"],
        },
    )
    assert rejected.status_code == 409, rejected.text
    assert "publish a stock-location policy release" in rejected.text


async def test_future_group_clear_blocks_early_warehouse_retirement(
    client,
    factory,
    tenant_a,
    native_retirement,
):
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user, permission=GROUPING)
    warehouse = await create_location(client, company, current, "FUTURE_CLEAR")
    group = await create_group(client, company, current, "REGION")
    today = dt.datetime.now(dt.UTC).astimezone(ZoneInfo("Asia/Kolkata")).date()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                WarehouseGroupAssignment(
                    id=uuid7(),
                    tenant_id=tenant_a,
                    company_id=company,
                    warehouse_id=uuid.UUID(warehouse),
                    group_id=uuid.UUID(group["id"]),
                    valid_from=today - dt.timedelta(days=10),
                    valid_to=None,
                )
            )
    future = today + dt.timedelta(days=5)
    scheduled = await assign(client, company, current, warehouse, None, future.isoformat())
    assert scheduled.status_code == 200, scheduled.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            edge = await db.scalar(
                select(WarehouseGroupAssignment).where(
                    WarehouseGroupAssignment.company_id == company,
                )
            )
            assert edge.valid_from <= today <= edge.valid_to
            assert await group_dependency(db, company, uuid.UUID(warehouse), today=today) is True
    retired = await retire(
        client,
        factory,
        tenant_a,
        company,
        warehouse,
        current,
        expected_version=scheduled.json()["row_version"],
    )
    assert retired.status_code == 409, retired.text
    assert "group membership" in retired.text
