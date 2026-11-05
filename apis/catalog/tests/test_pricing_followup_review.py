"""Regression coverage for the post-implementation pricing review."""

import uuid

import httpx
import pytest
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.pricing_storage_factories import seed_pricing
from tests.test_api import headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("owner", ["catalog.item", "catalog.product_family"])
@pytest.mark.parametrize(
    "route,key",
    [
        ("price-tiers", "item_price_tier"),
        ("price-formulas", "item_price_formula"),
        ("purchase-price-terms", "purchase_price_term"),
    ],
)
async def test_price_child_detail_requires_sku_and_family_authority(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    owner: str,
    route: str,
    key: str,
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    collection = f"/v1/companies/{company}/{route}"
    detail = collection + "/" + str(ids[key])
    allowed = await client.get(detail, headers=auth)
    assert allowed.status_code == 200, allowed.text
    await policy(factory, tenant_a, company, ids["actor_user"], owner, "name", "read", version=3)
    listing = await client.get(collection, headers=auth)
    assert listing.status_code == 403, listing.text
    denied = await client.get(detail, headers=auth)
    assert denied.status_code == 403, denied.text
