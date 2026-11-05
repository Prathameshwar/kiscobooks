"""Schema facts for sales_channel and the item_price_series channel binding."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import SalesChannel


def _channel(tenant: uuid.UUID, company: uuid.UUID, **changes: object) -> SalesChannel:
    values: dict[str, object] = {
        "id": uuid7(),
        "tenant_id": tenant,
        "company_id": company,
        "code": "WEB",
        "name": "Web store",
        "is_active": True,
        "row_version": 1,
        **changes,
    }
    return SalesChannel(**values)


async def test_sales_channel_is_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    scopes = ((tenant_a, uuid7()), (tenant_b, uuid7()))
    for tenant, company in scopes:
        with tenant_scope(tenant):
            async with factory.begin() as db:
                db.add(_channel(tenant, company))
    for tenant, _ in scopes:
        with tenant_scope(tenant):
            async with factory() as db:
                rows = list(await db.scalars(select(SalesChannel)))
                assert len(rows) == 1 and rows[0].tenant_id == tenant


async def test_sales_channel_code_is_unique_per_company(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(_channel(tenant_a, company))
    with tenant_scope(tenant_a), pytest.raises(IntegrityError):
        async with factory.begin() as db:
            db.add(_channel(tenant_a, company))
            await db.flush()


async def test_sales_channel_row_version_is_positive(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    with tenant_scope(tenant_a), pytest.raises(IntegrityError):
        async with factory.begin() as db:
            db.add(_channel(tenant_a, uuid7(), row_version=0))
            await db.flush()
