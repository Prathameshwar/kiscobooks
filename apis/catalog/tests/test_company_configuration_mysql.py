"""Atomic first-company drafts serialize through native MySQL company policy locks."""

import asyncio
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from catalog.models import ProductConfigurationDraft, ProductConfigurationScope
from tests.configuration_factories import setup_configuration
from tests.test_commercial_api import command_headers
from tests.test_company_product_defaults_mysql import native_defaults_factory  # noqa: F401

pytestmark = [pytest.mark.mysql, pytest.mark.usefixtures("stable_product_source_clock")]


@pytest.fixture
def engine(native_defaults_factory: async_sessionmaker[AsyncSession]) -> AsyncEngine:  # noqa: F811
    owner = native_defaults_factory.kw["bind"]
    assert isinstance(owner, AsyncEngine)
    return owner


async def test_concurrent_first_company_drafts_share_one_native_scope(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, _, auth, _ = await setup_configuration(factory, tenant_a)
    path = f"/v1/companies/{company}/product-configurations/company"

    async def save(reason: str) -> httpx.Response:
        return await client.post(
            path,
            headers=command_headers(auth),
            json={"effective_from": "2090-01-01", "change_reason": reason},
        )

    first, second = await asyncio.gather(save("Company draft one"), save("Company draft two"))
    assert first.status_code == second.status_code == 201, (first.text, second.text)
    assert first.json()["scope_id"] == second.json()["scope_id"]
    assert first.json()["id"] != second.json()["id"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductConfigurationScope.id))) == 1
            assert await db.scalar(select(func.count(ProductConfigurationDraft.id))) == 2
