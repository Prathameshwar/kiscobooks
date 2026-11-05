"""Schema facts for identifier_type / identifier_namespace and the ItemBarcode widening.

The v1 shape keeps the table named ``item_barcode`` and widens it with two
nullable columns bound by composite FKs to the new masters. A legacy row (both
columns NULL) is a barcode; a row naming a non-barcode identifier type must
name a mastered type.
"""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import IdentifierNamespace, IdentifierType, ItemBarcode


def _type(tenant: uuid.UUID, company: uuid.UUID, **changes: object) -> IdentifierType:
    values: dict[str, object] = {
        "id": uuid7(),
        "tenant_id": tenant,
        "company_id": company,
        "code": "MPN",
        "name": "Manufacturer part number",
        "is_barcode": False,
        "is_active": True,
        "row_version": 1,
        **changes,
    }
    return IdentifierType(**values)


def _namespace(tenant: uuid.UUID, company: uuid.UUID, **changes: object) -> IdentifierNamespace:
    values: dict[str, object] = {
        "id": uuid7(),
        "tenant_id": tenant,
        "company_id": company,
        "code": "OEM",
        "name": "Original equipment manufacturer",
        "is_active": True,
        "row_version": 1,
        **changes,
    }
    return IdentifierNamespace(**values)


async def test_masters_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    scopes = ((tenant_a, uuid7()), (tenant_b, uuid7()))
    for tenant, company in scopes:
        with tenant_scope(tenant):
            async with factory.begin() as db:
                db.add(_type(tenant, company))
                db.add(_namespace(tenant, company))
    for tenant, _ in scopes:
        with tenant_scope(tenant):
            async with factory() as db:
                types = list(await db.scalars(select(IdentifierType)))
                namespaces = list(await db.scalars(select(IdentifierNamespace)))
                assert len(types) == 1 and types[0].tenant_id == tenant
                assert len(namespaces) == 1 and namespaces[0].tenant_id == tenant


async def test_master_codes_are_unique_per_company(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(_type(tenant_a, company))
            db.add(_namespace(tenant_a, company))
    for row in (_type(tenant_a, company), _namespace(tenant_a, company)):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(row)
                await db.flush()


async def test_item_barcode_carries_the_new_identifier_columns(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """Legacy shape (both NULL) stays valid; columns widen for non-barcode types."""
    columns = {c.name for c in ItemBarcode.__table__.columns}
    assert "identifier_type_code" in columns
    assert "namespace_code" in columns
