"""Legacy rollout is explicit, tenant-scoped, resumable and non-destructive."""

import datetime as dt

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select

from catalog.models.product_authoring import CompanyProductAuthoringConfiguration as Mode
from catalog.tasks.product_mode_seed import LegacyCompany, LegacyRoster, seed


async def test_roster_seed_dry_run_resume_and_tenant_isolation(factory, tenant_a, tenant_b):
    company, operator = uuid7(), uuid7()
    roster = LegacyRoster(
        source="identity-company-roster",
        complete=True,
        cutoff_at=dt.datetime.now(dt.UTC),
        companies=[LegacyCompany(tenant_id=tenant_a, company_id=company)],
    )
    assert await seed(factory, roster, operator) == 1
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Mode.id))) == 0
    assert await seed(factory, roster, operator, apply=True) == 1
    assert await seed(factory, roster, operator, apply=True) == 0
    with tenant_scope(tenant_b):
        async with factory() as db:
            assert await db.scalar(select(func.count(Mode.id))) == 0
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = await db.scalar(select(Mode))
            row.product_family_sku_enabled = False
    assert await seed(factory, roster, operator, apply=True) == 0
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(Mode.product_family_sku_enabled)) is False


def test_roster_requires_explicit_complete_identity_source():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LegacyRoster.model_validate(
            {
                "source": "catalog-products",
                "complete": True,
                "cutoff_at": dt.datetime.now(dt.UTC),
                "companies": [],
            }
        )
