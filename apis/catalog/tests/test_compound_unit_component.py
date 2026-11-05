"""Schema facts for compound_unit_component.

Enforces the multiplicative shape at DB level: positive quantity, ordered
components, one component-row-per-position and a parent that is not itself.
"""

import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import CompoundUnitComponent, UnitOfMeasure


def _unit(tenant: uuid.UUID, company: uuid.UUID, **changes: object) -> UnitOfMeasure:
    values: dict[str, object] = {
        "id": uuid7(),
        "tenant_id": tenant,
        "company_id": company,
        "code": "KG",
        "symbol": "kg",
        "name": "Kilogram",
        "dimension": "MASS",
        "decimal_places": 4,
        "quantity_increment": Decimal("0.0001"),
        "is_active": True,
        "row_version": 1,
        **changes,
    }
    return UnitOfMeasure(**values)


def _component(
    tenant: uuid.UUID,
    company: uuid.UUID,
    parent: uuid.UUID,
    child: uuid.UUID,
    **changes: object,
) -> CompoundUnitComponent:
    values: dict[str, object] = {
        "id": uuid7(),
        "tenant_id": tenant,
        "company_id": company,
        "parent_unit_id": parent,
        "child_unit_id": child,
        "quantity": Decimal("12"),
        "ordinal": 1,
        "row_version": 1,
        **changes,
    }
    return CompoundUnitComponent(**values)


async def test_component_is_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    scopes = ((tenant_a, uuid7()), (tenant_b, uuid7()))
    for tenant, company in scopes:
        with tenant_scope(tenant):
            async with factory.begin() as db:
                parent = _unit(tenant, company, code="CASE", dimension="COUNT")
                child = _unit(tenant, company, code="BAG", dimension="COUNT")
                db.add(parent)
                db.add(child)
                await db.flush()
                db.add(_component(tenant, company, parent.id, child.id))
    for tenant, _ in scopes:
        with tenant_scope(tenant):
            async with factory() as db:
                rows = list(await db.scalars(select(CompoundUnitComponent)))
                assert len(rows) == 1 and rows[0].tenant_id == tenant


async def test_component_quantity_must_be_positive(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            parent = _unit(tenant_a, company, code="CASE", dimension="COUNT")
            child = _unit(tenant_a, company, code="BAG", dimension="COUNT")
            db.add(parent)
            db.add(child)
            await db.flush()
            parent_id, child_id = parent.id, child.id
    for quantity in (Decimal("0"), Decimal("-1")):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(_component(tenant_a, company, parent_id, child_id, quantity=quantity))
                await db.flush()


async def test_component_parent_cannot_be_the_child(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            unit = _unit(tenant_a, company)
            db.add(unit)
            await db.flush()
            uid = unit.id
    with tenant_scope(tenant_a), pytest.raises(IntegrityError):
        async with factory.begin() as db:
            db.add(_component(tenant_a, company, uid, uid))
            await db.flush()


async def test_component_positions_are_unique_per_parent(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            parent = _unit(tenant_a, company, code="CASE", dimension="COUNT")
            a = _unit(tenant_a, company, code="BAG", dimension="COUNT")
            b = _unit(tenant_a, company, code="BOX", dimension="COUNT")
            db.add_all([parent, a, b])
            await db.flush()
            parent_id, a_id, b_id = parent.id, a.id, b.id
            db.add(_component(tenant_a, company, parent_id, a_id, ordinal=1))
    with tenant_scope(tenant_a), pytest.raises(IntegrityError):
        async with factory.begin() as db:
            db.add(_component(tenant_a, company, parent_id, b_id, ordinal=1))
            await db.flush()
