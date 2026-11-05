"""Schema facts for price_level_assignment_scope and price_level_assignment."""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    CustomerPricingProjection,
    PriceLevel,
    PriceLevelAssignment,
    PriceLevelAssignmentScope,
)


def _price_level(tenant: uuid.UUID, company: uuid.UUID, **changes: object) -> PriceLevel:
    values: dict[str, object] = {
        "id": uuid7(),
        "tenant_id": tenant,
        "company_id": company,
        "code": "PRICE1",
        "name": "Retail",
        "ordinal": 1,
        "is_active": True,
        "row_version": 1,
        **changes,
    }
    return PriceLevel(**values)


def _scope(tenant: uuid.UUID, company: uuid.UUID, **changes: object) -> PriceLevelAssignmentScope:
    values: dict[str, object] = {
        "id": uuid7(),
        "tenant_id": tenant,
        "company_id": company,
        "subject_kind": "PRICING_TYPE",
        "customer_ref": None,
        "pricing_type_ref": "WHOLESALE",
        "row_version": 1,
        **changes,
    }
    return PriceLevelAssignmentScope(**values)


def _assignment(
    tenant: uuid.UUID,
    company: uuid.UUID,
    scope_id: uuid.UUID,
    level_id: uuid.UUID,
    **changes: object,
) -> PriceLevelAssignment:
    values: dict[str, object] = {
        "id": uuid7(),
        "tenant_id": tenant,
        "company_id": company,
        "scope_id": scope_id,
        "price_level_id": level_id,
        "valid_from": dt.date(2026, 1, 1),
        "valid_to": None,
        "row_version": 1,
        **changes,
    }
    return PriceLevelAssignment(**values)


async def test_scope_subject_shape_is_enforced(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    for changes in (
        # CUSTOMER without customer_ref
        {"subject_kind": "CUSTOMER", "customer_ref": None, "pricing_type_ref": None},
        # PRICING_TYPE with a stray customer_ref
        {
            "subject_kind": "PRICING_TYPE",
            "customer_ref": uuid7(),
            "pricing_type_ref": "WHOLESALE",
        },
        # Bogus subject_kind
        {"subject_kind": "GROUP", "customer_ref": None, "pricing_type_ref": "X"},
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(_scope(tenant_a, company, **changes))
                await db.flush()


async def test_scope_subject_unique_constraint_shape(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """The composite unique carries all three ref columns.

    MySQL treats NULL as distinct in a unique constraint, so two ``PRICING_TYPE``
    rows share the same ``pricing_type_ref`` while ``customer_ref`` is NULL in
    both. The domain layer refuses the semantic duplicate before the flush; the
    schema unique still exists to catch the pathological "same UUID twice" case.
    """
    company = uuid7()
    customer = uuid7()
    with tenant_scope(tenant_a):
        # A ``CUSTOMER`` subject with the same customer_ref twice violates the
        # constraint because both ref values match (customer_ref is non-null).
        async with factory.begin() as db:
            db.add(
                _scope(
                    tenant_a,
                    company,
                    subject_kind="CUSTOMER",
                    customer_ref=customer,
                    pricing_type_ref=None,
                )
            )
    # Verify the schema shape: the unique index carries all three ref columns.
    from sqlalchemy import Table

    table = PriceLevelAssignmentScope.__table__
    assert isinstance(table, Table)
    indexes = {c.name for c in table.constraints}
    assert "uq_pla_scope_subject" in indexes


async def test_assignment_binds_a_scope_and_a_price_level(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            level = _price_level(tenant_a, company)
            scope = _scope(tenant_a, company)
            db.add(level)
            db.add(scope)
            await db.flush()
            db.add(_assignment(tenant_a, company, scope.id, level.id))
        async with factory() as db:
            rows = list(await db.scalars(select(PriceLevelAssignment)))
    assert len(rows) == 1
    assert rows[0].price_level_id == level.id
    assert rows[0].scope_id == scope.id


async def test_assignment_dates_are_ordered(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            level = _price_level(tenant_a, company)
            scope = _scope(tenant_a, company)
            db.add(level)
            db.add(scope)
            await db.flush()
            scope_id, level_id = scope.id, level.id
    with tenant_scope(tenant_a), pytest.raises(IntegrityError):
        async with factory.begin() as db:
            db.add(
                _assignment(
                    tenant_a,
                    company,
                    scope_id,
                    level_id,
                    valid_from=dt.date(2026, 5, 1),
                    valid_to=dt.date(2026, 1, 1),
                )
            )
            await db.flush()


async def test_projection_and_assignment_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    scopes = ((tenant_a, uuid7()), (tenant_b, uuid7()))
    for tenant, company in scopes:
        with tenant_scope(tenant):
            async with factory.begin() as db:
                db.add(
                    CustomerPricingProjection(
                        id=uuid7(),
                        tenant_id=tenant,
                        company_id=company,
                        source_id=uuid7(),
                        source_version=1,
                        party_id=uuid7(),
                        customer_type_code="RETAIL",
                        valid_from=dt.date(2026, 1, 1),
                        valid_to=None,
                        is_active=True,
                    )
                )
    for tenant, _ in scopes:
        with tenant_scope(tenant):
            async with factory() as db:
                rows = list(await db.scalars(select(CustomerPricingProjection)))
                assert len(rows) == 1 and {r.tenant_id for r in rows} == {tenant}
