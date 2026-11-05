import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.handling import (
    HandlingProfile,
    HandlingProfileRevision,
)
from tests.handling_factories import seed_profile


async def test_handling_profile_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    scopes = ((tenant_a, uuid7()), (tenant_b, uuid7()))
    for tenant, company in scopes:
        await seed_profile(factory, tenant, company)
    for tenant, company in scopes:
        with tenant_scope(tenant):
            async with factory() as db:
                for model in (HandlingProfile, HandlingProfileRevision):
                    rows = list(await db.scalars(select(model)))
                    assert len(rows) == 1
                    assert isinstance(rows[0], HandlingProfile | HandlingProfileRevision)
                    assert rows[0].company_id == company and rows[0].tenant_id == tenant


async def test_handling_storage_enforces_scoped_exact_ordered_bounds(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, other = uuid7(), uuid7()
    own, _ = await seed_profile(factory, tenant_a, company)
    foreign, _ = await seed_profile(factory, tenant_a, other)
    valid = {
        "tenant_id": tenant_a,
        "company_id": company,
        "profile_id": own,
        "revision": 2,
        "row_version": 1,
        "fragile": False,
        "keep_dry": False,
        "keep_upright": False,
    }
    for changes in (
        {"profile_id": foreign},
        {"revision": 1},
        {"revision": 0},
        {"row_version": 0},
        {"temperature_unit": "CELSIUS"},
        {"temperature_min": Decimal("2")},
        {"temperature_min": Decimal("2"), "temperature_unit": "FAHRENHEIT"},
        {
            "temperature_min": Decimal("9"),
            "temperature_max": Decimal("8"),
            "temperature_unit": "CELSIUS",
        },
        {"temperature_min": Decimal("-273.1501"), "temperature_unit": "CELSIUS"},
        {"temperature_max": Decimal("-273.1501"), "temperature_unit": "CELSIUS"},
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(HandlingProfileRevision(**{**valid, **changes}))
                await db.flush()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = HandlingProfileRevision(
                **valid, temperature_min=Decimal("2.1234"), temperature_unit="CELSIUS"
            )
            db.add(row)
            await db.flush()
            identity = row.id
        async with factory() as db:
            stored = await db.get(HandlingProfileRevision, identity)
            assert stored is not None and isinstance(stored.temperature_min, Decimal)
            assert stored.temperature_min == Decimal("2.1234")
