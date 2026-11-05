import datetime as dt
import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ItemGroupParent, ProductPricingPolicy
from catalog.models import pricing as m
from tests.pricing_factories import create, guard
from tests.pricing_storage_factories import seed_pricing
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_pricing_resolution import query

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_commercial_bounds_recompute_estimates_and_require_real_context(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"

    async def result(expected: int = 200) -> dict[str, object]:
        response = await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
        assert response.status_code == expected, response.text
        return dict(response.json())

    assert (await result())["status"] == "NEEDS_TAX_CONTEXT"
    async with changed(
        factory, tenant_a, m.ItemMrp, ids["item_mrp"], valid_from=dt.date(2091, 1, 1)
    ):
        assert (await result())["minimum_rate"] == {"numerator": "50", "denominator": "1"}
        async with changed(
            factory,
            tenant_a,
            m.CommercialGuardRule,
            ids["commercial_guard_rule"],
            rule_kind="FIXED_MAX",
        ):
            await result(409)
        async with changed(
            factory,
            tenant_a,
            m.CommercialGuardRule,
            ids["commercial_guard_rule"],
            amount=Decimal(150),
        ):
            await result(409)
            async with changed(
                factory,
                tenant_a,
                m.CommercialGuardRule,
                ids["commercial_guard_rule"],
                severity="REQUIRE_APPROVAL",
            ):
                approval = await result()
                assert approval["approval_guard_ids"] == [str(ids["commercial_guard_rule"])]
                assert approval["final_guard_validation_required"] is True
        async with changed(
            factory,
            tenant_a,
            m.CommercialGuardRule,
            ids["commercial_guard_rule"],
            rule_kind="MIN_MARGIN",
            amount=None,
            percentage=Decimal(20),
            estimate_kind="STANDARD_ESTIMATE",
        ):
            assert (await result())["minimum_rate"] == {"numerator": "100", "denominator": "1"}
            async with changed(
                factory,
                tenant_a,
                m.ItemReferenceCost,
                ids["item_reference_cost"],
                valid_from=dt.date(2091, 1, 1),
            ):
                await result(409)
        async with changed(
            factory,
            tenant_a,
            ItemGroupParent,
            ids["item_group_parent"],
            valid_from=dt.date(2091, 1, 1),
        ):
            await result(409)
        async with changed(
            factory,
            tenant_a,
            ProductPricingPolicy,
            ids["product_pricing_policy"],
            mrp_mode="REQUIRED",
        ):
            await result(409)
    # Inclusive book and a declaration, without active tax-exclusive guards, compare directly.
    async with changed(factory, tenant_a, m.PricePlan, ids["price_plan"], tax_basis="INCLUSIVE"):
        async with changed(
            factory,
            tenant_a,
            m.CommercialGuardRule,
            ids["commercial_guard_rule"],
            valid_from=dt.date(2091, 1, 1),
        ):
            assert (await result())["maximum_rate"] == {"numerator": "120", "denominator": "1"}
            async with changed(factory, tenant_a, m.ItemMrp, ids["item_mrp"], amount=Decimal(90)):
                await result(409)


async def test_discount_owners_combine_and_detail_checks_their_references(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    discounts = []
    for kind, field, key, amount in (
        ("GROUP", "group_id", "item_group", "9"),
        ("FAMILY", "family_id", "product_family", "8"),
        ("SKU", "item_id", "item", "3"),
    ):
        scope = await create(
            client,
            root,
            auth,
            "/commercial-policy-scopes",
            {"owner_kind": kind, field: str(ids[key])},
        )
        discount = await create(
            client,
            root,
            auth,
            "/discount-ceilings",
            {
                **guard(scope),
                "scope_id": scope["id"],
                "valid_from": "2090-01-01",
                "max_discount_pct": amount,
            },
        )
        discounts.append(discount["id"])
        detail = await client.get(root + "/discount-ceilings/" + discount["id"], headers=auth)
        assert detail.status_code == 200, detail.text
    result = await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
    assert result.status_code == 200 and result.json()["max_discount_pct"] == "3.0000", result.text
    assert set(discounts) <= set(result.json()["guard_ids"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                m.CommercialGuardRule(
                    tenant_id=tenant_a,
                    company_id=company,
                    item_id=ids["item"],
                    unit_revision_id=ids["item_unit_revision"],
                    numeric_revision_id=ids["item_price_numeric_revision"],
                    currency="INR",
                    valid_from=dt.date(2090, 1, 1),
                    rule_kind="FIXED_MAX",
                    amount="40",
                    price_basis_quantity="1",
                    tax_basis="EXCLUSIVE",
                    severity="BLOCK",
                    source_reference="Reviewed",
                )
            )
    conflict = await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
    assert conflict.status_code == 409, conflict.text
