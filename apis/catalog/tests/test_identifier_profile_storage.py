import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.profiles import IdentifierProfile, IdentifierProfileRequirement
from tests.profile_factories import seed_identifier_profile


async def test_identifier_profile_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    companies = (uuid7(), uuid7())
    for tenant, company in zip((tenant_a, tenant_b), companies, strict=True):
        await seed_identifier_profile(factory, tenant, company)
    for tenant, company in zip((tenant_a, tenant_b), companies, strict=True):
        with tenant_scope(tenant):
            async with factory() as db:
                for model in (IdentifierProfile, IdentifierProfileRequirement):
                    rows = list(await db.scalars(select(model)))
                    assert len(rows) == 1
                    assert isinstance(rows[0], IdentifierProfile | IdentifierProfileRequirement)
                    assert rows[0].tenant_id == tenant and rows[0].company_id == company


async def test_identifier_requirement_storage_rejects_invalid_scope_type_and_counts(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, other = uuid7(), uuid7()
    own = await seed_identifier_profile(factory, tenant_a, company)
    foreign = await seed_identifier_profile(factory, tenant_a, other)
    valid = {
        "tenant_id": tenant_a,
        "company_id": company,
        "profile_id": own,
        "identifier_type": "SERIAL",
        "namespace_rule": "MANUFACTURER_SKU",
        "min_count": 1,
        "max_count": 1,
        "requires_slot": False,
    }
    for changes in (
        {"profile_id": foreign},
        {"max_count": 9},
        {"min_count": 2},
        {"max_count": 2},
        {"namespace_rule": "TENANT"},
        {"identifier_type": "IMEI"},
        {"identifier_type": "IMEISV"},
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(IdentifierProfileRequirement(**{**valid, **changes}))
                await db.flush()
    with tenant_scope(tenant_a), pytest.raises(IntegrityError):
        async with factory.begin() as db:
            db.add(
                IdentifierProfile(
                    tenant_id=tenant_a,
                    company_id=company,
                    code="BAD",
                    name="Bad",
                    normalization_version=2,
                )
            )
            await db.flush()
