"""Fresh coordinated NoStock proof, immutable history and final transaction fences."""

import datetime as dt
import uuid
from dataclasses import replace

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select

from catalog.domain.warehouse_resolution import REJECTED
from catalog.models.classification import CatalogPolicyState
from catalog.models.releases import CatalogPolicyConsumerAck
from catalog.models.stock_source import RETIREMENT_CHECKS, RetirementClearance, StockSourceFence
from catalog.models.warehouses import Warehouse
from tests.test_policy_release_api import deactivate, provision
from tests.warehouse_factories import clear_retirement, publish_release


async def prepared(client, factory, tenant):
    fixture = await provision(client, factory, tenant, godowns=("GD1",))
    release = await publish_release(client, fixture["company"], fixture["current"])
    return fixture, release


async def test_old_rejected_nostock_can_be_refreshed_by_current_native_proof(
    client, factory, tenant_a, native_retirement
):
    state, release = await prepared(client, factory, tenant_a)
    company, identity = state["company"], state["locations"]["GD1"]
    await clear_retirement(
        factory,
        tenant_a,
        company,
        uuid.UUID(identity),
        release=release,
        result=REJECTED,
        reason_code="STOCK_ON_HAND",
    )
    result = await deactivate(client, company, identity, state["current"])
    assert result.status_code == 200, result.text
    assert len(native_retirement.checks) == 2 and len(native_retirement.releases) == 1
    with tenant_scope(tenant_a):
        async with factory() as db:
            ack = await db.scalar(
                select(CatalogPolicyConsumerAck).where(
                    CatalogPolicyConsumerAck.aggregate_id == uuid.UUID(identity),
                )
            )
            assert ack.result == "APPLIED" and ack.row_version == 2
            assert ack.source_message_id == native_retirement.checks[-1][1].check_id


@pytest.mark.parametrize("wrong_hash", [False, True])
async def test_failure_after_document_lease_releases_it_and_keeps_location_active(
    client, factory, tenant_a, native_retirement, wrong_hash
):
    state, _ = await prepared(client, factory, tenant_a)
    company, identity = state["company"], state["locations"]["GD1"]
    if wrong_hash:
        native_retirement.wrong_hash_owner = "accounting"
    else:
        native_retirement.unavailable_owner = "accounting"
    failed = await deactivate(client, company, identity, state["current"])
    assert failed.status_code == 503, failed.text
    assert len(native_retirement.releases) == 1
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (await db.get(Warehouse, uuid.UUID(identity))).is_active is True


async def test_live_stock_source_lease_prevents_retirement_before_owner_calls(
    client, factory, tenant_a, native_retirement
):
    state, _ = await prepared(client, factory, tenant_a)
    company, identity = state["company"], state["locations"]["GD1"]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                StockSourceFence(
                    id=uuid7(),
                    tenant_id=tenant_a,
                    company_id=company,
                    execution_id=uuid7(),
                    actor_user_id=state["user"],
                    request_hash="a" * 64,
                    expires_at=utcnow() + dt.timedelta(seconds=30),
                    facts={},
                )
            )
    denied = await deactivate(client, company, identity, state["current"])
    assert denied.status_code == 409, denied.text
    assert "stock posting" in denied.json()["error"]["message"]
    assert native_retirement.checks == []


async def local_warehouse(factory, tenant):
    company, identity = uuid7(), uuid7()
    with tenant_scope(tenant):
        async with factory.begin() as db:
            db.add(CatalogPolicyState(tenant_id=tenant, company_id=company, generation=1))
            db.add(
                Warehouse(
                    id=identity,
                    tenant_id=tenant,
                    company_id=company,
                    code="SPARE",
                    name="Spare godown",
                    kind="GODOWN",
                    is_active=True,
                    is_system=False,
                    row_version=1,
                )
            )
    return company, identity


async def test_orm_retirement_requires_current_scope_bound_clearance(factory, tenant_a):
    company, identity = await local_warehouse(factory, tenant_a)
    with tenant_scope(tenant_a):
        with pytest.raises(ConflictError, match="NoStock"):
            async with factory.begin() as db:
                row = await db.get(Warehouse, identity)
                row.is_active = False
        with pytest.raises(ConflictError, match="NoStock"):
            async with factory.begin() as db:
                row = await db.get(Warehouse, identity)
                db.info[RETIREMENT_CHECKS] = {
                    ("warehouse", identity): RetirementClearance(
                        tenant_id=uuid7(),
                        company_id=company,
                        table_name="warehouse",
                        object_id=identity,
                        expected_version=1,
                        check_id=uuid7(),
                        checked_at=utcnow(),
                        expires_at=utcnow() + dt.timedelta(seconds=30),
                    )
                }
                row.is_active = False


async def test_savepoint_commit_does_not_discard_final_expiry_check(factory, tenant_a):
    company, identity = await local_warehouse(factory, tenant_a)
    with tenant_scope(tenant_a):
        with pytest.raises(ConflictError, match="expired"):
            async with factory.begin() as db:
                row = await db.get(Warehouse, identity)
                check = RetirementClearance(
                    tenant_id=tenant_a,
                    company_id=company,
                    table_name="warehouse",
                    object_id=identity,
                    expected_version=1,
                    check_id=uuid7(),
                    checked_at=utcnow(),
                    expires_at=utcnow() + dt.timedelta(seconds=30),
                )
                db.info[RETIREMENT_CHECKS] = {("warehouse", identity): check}
                row.is_active, row.row_version = False, 2
                await db.flush()
                async with db.begin_nested():
                    assert (
                        await db.scalar(select(Warehouse.id).where(Warehouse.id == identity))
                        == identity
                    )
                assert db.info[RETIREMENT_CHECKS][("warehouse", identity)] == check
                db.info[RETIREMENT_CHECKS][("warehouse", identity)] = replace(
                    check,
                    expires_at=utcnow() - dt.timedelta(seconds=1),
                )
        async with factory() as db:
            row = await db.get(Warehouse, identity)
            assert row.is_active is True and row.row_version == 1
