"""Party and customer-type projections — schema-level tenant isolation and identity.

Both tables are ingested from Billing, never written from a Catalog route. Here we
verify the schema facts the ingestion path will rely on: tenant isolation, source
identity uniqueness and the source-version monotonic constraint.
"""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import CustomerTypeProjection, PartyProjection


def party(tenant: uuid.UUID, company: uuid.UUID, **changes: object) -> PartyProjection:
    values: dict[str, object] = {
        "id": uuid7(),
        "tenant_id": tenant,
        "company_id": company,
        "source_id": uuid7(),
        "source_version": 1,
        "party_kind": "CUSTOMER",
        "code": "P1",
        "display_name": "Acme",
        "status": "active",
        "country_code": "IN",
        **changes,
    }
    return PartyProjection(**values)


def customer_type(
    tenant: uuid.UUID, company: uuid.UUID, **changes: object
) -> CustomerTypeProjection:
    values: dict[str, object] = {
        "id": uuid7(),
        "tenant_id": tenant,
        "company_id": company,
        "source_id": uuid7(),
        "source_version": 1,
        "code": "RETAIL",
        "display_name": "Retail",
        "parent_code": None,
        "is_active": True,
        **changes,
    }
    return CustomerTypeProjection(**values)


async def test_projection_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    scopes = ((tenant_a, uuid7()), (tenant_b, uuid7()))
    for tenant, company in scopes:
        with tenant_scope(tenant):
            async with factory.begin() as db:
                db.add(party(tenant, company))
                db.add(customer_type(tenant, company))
    for tenant, _ in scopes:
        with tenant_scope(tenant):
            async with factory() as db:
                parties = list(await db.scalars(select(PartyProjection)))
                types = list(await db.scalars(select(CustomerTypeProjection)))
                assert len(parties) == 1 and {row.tenant_id for row in parties} == {tenant}
                assert len(types) == 1 and {row.tenant_id for row in types} == {tenant}


async def test_projection_rows_are_source_identity_unique(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    source = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(party(tenant_a, company, source_id=source))
            db.add(customer_type(tenant_a, company, source_id=source))
    for row in (
        party(tenant_a, company, source_id=source),
        customer_type(tenant_a, company, source_id=source),
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(row)
                await db.flush()


async def test_source_version_is_positive(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    for row in (
        party(tenant_a, company, source_version=0),
        customer_type(tenant_a, company, source_version=0),
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(row)
                await db.flush()
