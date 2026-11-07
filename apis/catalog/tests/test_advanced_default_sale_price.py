"""Advanced capture includes the protected default book without enabling extra levels."""

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select

from catalog.models.configuration import ProductPricingPolicy
from catalog.models.pricing import CompanyPricingPolicy, PriceLevel
from tests.product_factories import setup_product
from tests.test_advanced_product_drafts import PERMISSIONS
from tests.test_api import headers
from tests.test_product_mode import set_mode
from tests.test_simple_product_creation import starter

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("kind", ["GOODS", "SERVICE"])
@pytest.mark.parametrize("required", [False, True])
async def test_advanced_default_book_available_with_multiple_levels_disabled(
    client, factory, tenant_a, kind, required
):
    root, auth, _ = await starter(factory, tenant_a, inventory=True)
    company = root.rsplit("/", 1)[-1]
    changed, _, _ = await set_mode(client, company, auth, True)
    assert changed.status_code == 200, changed.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            configs = list(await db.scalars(select(ProductPricingPolicy)))
            for config in configs:
                config.sale_price_mode = "REQUIRED" if required else "OPTIONAL"
                config.multiple_price_levels_mode = "DISABLED"
                config.sale_level_count = 1
            policy = await db.scalar(select(CompanyPricingPolicy))
            default_id = str(policy.default_level_id)
            # An unused extra level must not leak into single-level capture or demand a book.
            level = await db.scalar(select(PriceLevel))
            db.add(PriceLevel(
                id=uuid7(), tenant_id=tenant_a, company_id=level.company_id,
                code="UNUSED", name="Unused extra level", ordinal=2, is_active=True,
            ))
    result = await client.get(
        root + "/advanced-product-creations/options?kind=" + kind, headers=auth
    )
    assert result.status_code == 200, result.text
    choices = result.json()["sale_price_levels"]
    assert len(choices) == 1
    assert choices[0]["price_level_id"] == default_id
    assert choices[0]["is_default"] is True
    assert choices[0]["required"] is required
    assert choices[0]["plan_id"]
    assert choices[0]["tax_basis"] in {"EXCLUSIVE", "INCLUSIVE"}


async def test_simple_scalar_capture_keeps_its_existing_contract(client, factory, tenant_a):
    root, auth, _ = await starter(factory, tenant_a)
    result = await client.get(root + "/simple-product-creations/options?kind=GOODS", headers=auth)
    assert result.status_code == 200, result.text
    assert result.json()["sale_price_levels"] == []
    assert "sale_price" in {field["key"] for field in result.json()["fields"]}


async def test_optional_draft_capture_remains_available_before_pricing_bootstrap(
    client, factory, tenant_a
):
    company, user, _, _ = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=PERMISSIONS)
    result = await client.get(
        f"/v1/companies/{company}/advanced-product-creations/options", headers=auth
    )
    assert result.status_code == 200, result.text
    assert result.json()["defaults"]["configuration"]["pricing"]["sale_price_mode"] == "OPTIONAL"
    assert result.json()["sale_price_levels"] == []
