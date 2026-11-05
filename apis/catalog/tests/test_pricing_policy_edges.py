import datetime as dt
import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    Item,
    ItemGroup,
    ItemGroupParent,
    ItemUnitRevision,
    ProductFamily,
    ProductPricingPolicy,
    ProductTypeRevision,
)
from catalog.models import pricing as m
from catalog.tasks.pricing_foundation import basis
from tests.pricing_factories import create, guard
from tests.pricing_storage_factories import seed_pricing
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_pricing_boundaries import draft_body
from tests.test_pricing_levels_units import feature
from tests.test_pricing_resolution import query, reference

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_level_capabilities_fallback_publication_and_commercial_policy(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    custom = {"code": "TRADE", "name": "Trade", "ordinal": 4}
    denied = await client.post(root + "/price-levels", headers=command_headers(auth), json=custom)
    assert denied.status_code == 409, denied.text
    await feature(factory, tenant_a, company, ids["actor_user"])
    denied = await client.post(
        root + "/price-levels", headers=command_headers(auth), json={**custom, "ordinal": 2}
    )
    assert denied.status_code == 422, denied.text
    token = await create(client, root, auth, "/pricing/bootstrap", {})
    levels = await client.get(root + "/price-levels", headers=auth)
    second = next(value for value in levels.json()["items"] if value["ordinal"] == 2)
    policy = {
        **guard(token),
        "default_level_id": str(ids["price_level"]),
        "fallback_level_id": second["id"],
        "missing_price_policy": "FALLBACK",
        "valid_from": "2091-01-01",
        "supersedes_id": str(ids["company_pricing_policy"]),
        "expected_previous_version": 1,
    }
    wrong = await client.post(
        root + "/company-pricing-policies",
        headers=command_headers(auth),
        json={**policy, "purchase_plan_id": str(ids["price_plan"])},
    )
    assert wrong.status_code == 422, wrong.text
    token = await create(client, root, auth, "/company-pricing-policies", policy)
    commercial = {
        **guard(token),
        "item_id": str(ids["item"]),
        "free_sale_allowed": True,
        "valid_from": "2091-01-01",
        "supersedes_id": str(ids["item_commercial_policy"]),
        "expected_previous_version": 1,
    }
    async with changed(factory, tenant_a, Item, ids["item"], sellable=False):
        rejected = await client.post(
            root + "/item-commercial-policies", headers=command_headers(auth), json=commercial
        )
        assert rejected.status_code == 409, rejected.text
        guard_body = {
            **guard(token),
            "item_id": str(ids["item"]),
            "unit_revision_id": str(ids["item_unit_revision"]),
            "numeric_revision_id": str(ids["item_price_numeric_revision"]),
            "currency": "INR",
            "valid_from": "2091-01-01",
            "rule_kind": "FIXED_MAX",
            "amount": "200",
            "price_basis_quantity": "1",
            "tax_basis": "EXCLUSIVE",
            "severity": "BLOCK",
            "source_reference": "Reviewed",
        }
        rejected = await client.post(
            root + "/commercial-guard-rules", headers=command_headers(auth), json=guard_body
        )
        assert rejected.status_code == 409, rejected.text
    await create(client, root, auth, "/item-commercial-policies", commercial)
    await feature(factory, tenant_a, company, ids["actor_user"], version=4, enabled=False)
    denied = await client.post(
        root + "/prices/resolve",
        headers=auth,
        json=query(ids, price_level_id=second["id"], override_reason="Review"),
    )
    assert denied.status_code == 409, denied.text


async def test_incomplete_ancestry_empty_discount_scope_and_service_mrp_fail_closed(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    async with changed(
        factory, tenant_a, ItemGroupParent, ids["item_group_parent"], valid_from=dt.date(2091, 1, 1)
    ):
        rejected = await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
        assert rejected.status_code == 409 and "ancestry" in rejected.text, rejected.text
    async with changed(
        factory,
        tenant_a,
        m.DiscountCeiling,
        ids["discount_ceiling"],
        valid_from=dt.date(2091, 1, 1),
    ):
        resolved = await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
        assert (
            resolved.status_code == 200 and resolved.json()["max_discount_pct"] is None
        ), resolved.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            pricing = await db.scalar(
                select(ProductPricingPolicy).where(ProductPricingPolicy.revision_id.is_not(None))
            )
            assert pricing is not None
            pricing_id = pricing.id
            family = await db.get(ProductFamily, ids["product_family"])
            assert family is not None
            type_revision_id = family.product_type_revision_id
    async with (
        changed(factory, tenant_a, ProductFamily, ids["product_family"], kind="SERVICE"),
        changed(
            factory,
            tenant_a,
            ProductTypeRevision,
            type_revision_id,
            kind="SERVICE",
            inventory_modes=["NON_STOCK"],
            tracking_modes=["NONE"],
        ),
        changed(factory, tenant_a, ItemGroup, ids["item_group"], allowed_kind="BOTH"),
    ):
        async with changed(
            factory, tenant_a, ProductPricingPolicy, pricing_id, mrp_mode="REQUIRED"
        ):
            sale = await client.post(
                root + "/price-drafts", headers=command_headers(auth), json=draft_body(ids)
            )
            assert sale.status_code == 201, sale.text
            # Shared goods defaults cannot block service sale pricing, but a service
            # still cannot acquire its own physical product MRP declaration.
            rejected = await client.post(
                root + "/product-mrps",
                headers=command_headers(auth),
                json=reference(
                    ids,
                    {"numeric": {"id": str(ids["item_price_numeric_revision"])}},
                    sale.json(),
                    jurisdiction="IN",
                ),
            )
            assert rejected.status_code == 409 and "eligible goods" in rejected.text, rejected.text


def test_fractional_basis_must_respect_entry_policy_even_when_on_numeric_grid() -> None:
    revision = ItemUnitRevision(
        quantity_decimal_places=2, quantity_increment=Decimal("0.25"), fractional_entry=False
    )
    with pytest.raises(ValidationFailedError, match="fractional"):
        basis(revision, Decimal("1.25"))
