import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.returns import (
    ReturnPolicy,
    ReturnPolicyCondition,
    ReturnPolicyRevision,
)
from tests.return_factories import seed_policy


async def test_return_policy_tables_are_tenant_isolated(
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
                for model in (ReturnPolicy, ReturnPolicyRevision, ReturnPolicyCondition):
                    rows = list(await db.scalars(select(model)))
                    assert len(rows) == (2 if model is ReturnPolicyCondition else 1)
                    for row in rows:
                        assert isinstance(
                            row, ReturnPolicy | ReturnPolicyRevision | ReturnPolicyCondition
                        )
                        assert row.company_id == company and row.tenant_id == tenant


async def test_return_storage_enforces_scope_windows_and_fixed_conditions(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, other = uuid7(), uuid7()
    own, revision = await seed_policy(factory, tenant_a, company)
    foreign, foreign_revision = await seed_policy(factory, tenant_a, other)
    valid = {
        "tenant_id": tenant_a,
        "company_id": company,
        "policy_id": own,
        "revision": 2,
        "row_version": 1,
        "returns_allowed": True,
        "window_days": 30,
        "condition_count": 0,
    }
    for changes in (
        {"policy_id": foreign},
        {"revision": 1},
        {"revision": 0},
        {"row_version": 0},
        {"window_days": None},
        {"window_days": -1},
        {"window_days": 36501},
        {"condition_count": -1},
        {"condition_count": 6},
        {"returns_allowed": False},
        {"returns_allowed": False, "window_days": None, "condition_count": 1},
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(ReturnPolicyRevision(**{**valid, **changes}))
                await db.flush()
    for target, code in (
        (foreign_revision, "UNUSED"),
        (revision, "UNUSED"),
        (revision, "REFUND_ALL"),
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(
                    ReturnPolicyCondition(
                        tenant_id=tenant_a,
                        company_id=company,
                        revision_id=target,
                        condition_code=code,
                    )
                )
                await db.flush()
