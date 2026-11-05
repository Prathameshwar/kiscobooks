import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.warranties import (
    WarrantyPolicy,
    WarrantyPolicyRevision,
)
from tests.warranty_factories import seed_policy


async def test_warranty_policy_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    scopes = ((tenant_a, uuid7()), (tenant_b, uuid7()))
    for tenant, company in scopes:
        await seed_policy(factory, tenant, company)
    for tenant, company in scopes:
        with tenant_scope(tenant):
            async with factory() as db:
                for model in (WarrantyPolicy, WarrantyPolicyRevision):
                    rows = list(await db.scalars(select(model)))
                    assert len(rows) == 1
                    assert isinstance(rows[0], WarrantyPolicy | WarrantyPolicyRevision)
                    assert rows[0].company_id == company and rows[0].tenant_id == tenant


async def test_warranty_storage_enforces_scope_identity_and_calendar_duration(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, other = uuid7(), uuid7()
    own, _ = await seed_policy(factory, tenant_a, company)
    foreign, _ = await seed_policy(factory, tenant_a, other)
    valid = {
        "tenant_id": tenant_a,
        "company_id": company,
        "policy_id": own,
        "revision": 2,
        "row_version": 1,
        "duration": 12,
        "duration_unit": "MONTHS",
        "start_trigger": "SALE",
    }
    for changes in (
        {"policy_id": foreign},
        {"revision": 1},
        {"revision": 0},
        {"row_version": 0},
        {"duration": 0},
        {"duration": 1201},
        {"duration_unit": "DAYS", "duration": 36501},
        {"duration_unit": "YEARS", "duration": 101},
        {"duration_unit": "ANY"},
        {"start_trigger": "ANY"},
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(WarrantyPolicyRevision(**{**valid, **changes}))
                await db.flush()
