import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, PackType
from catalog.models import pricing as m
from catalog.models.product_definitions import ItemUnitRevision
from tests.pricing_factories import create
from tests.pricing_storage_factories import seed_pricing
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy
from tests.test_pricing_boundaries import draft_body
from tests.test_pricing_resolution import query

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_ambiguous_price_histories_and_oversized_native_aggregates_fail_closed(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                m.CompanyPricingPolicy(
                    tenant_id=tenant_a,
                    company_id=company,
                    default_level_id=ids["price_level"],
                    missing_price_policy="ERROR",
                    sale_unit_mode="EXPLICIT_ONLY",
                    purchase_unit_mode="EXPLICIT_ONLY",
                    valid_from=dt.date(2089, 1, 1),
                )
            )
    result = await client.post(root + "/prices/coverage", headers=auth, json=query(ids))
    assert result.status_code == 409 and "ambiguous" in result.text, result.text
    # Restore the non-overlapping dated definition and make the price aggregate malformed.
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            old = await db.scalar(
                select(m.CompanyPricingPolicy).where(
                    m.CompanyPricingPolicy.valid_from == dt.date(2089, 1, 1)
                )
            )
            assert old is not None
            old.valid_to = dt.date(2089, 12, 31)
            for index in range(1, 65):
                db.add(
                    m.ItemPriceTier(
                        tenant_id=tenant_a,
                        company_id=company,
                        price_id=ids["item_price"],
                        min_quantity=Decimal(index),
                        max_quantity=None,
                        amount=Decimal(100),
                        currency="INR",
                    )
                )
    result = await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
    assert result.status_code == 409 and "bounded" in result.text, result.text


async def test_read_denies_also_protect_pricing_filters_search_and_children(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    for version, (entity, field, path, params) in enumerate(
        (
            ("price_plan", "purpose", "/price-plans/" + str(ids["price_plan"]), {}),
            ("item_price", "currency", "/prices", {"currency": "INR"}),
            ("item_price", "valid_from", "/prices", {"as_of": "2090-01-01"}),
            ("price_level", "name", "/price-levels", {"q": "Retail"}),
        ),
        3,
    ):
        await policy(
            factory,
            tenant_a,
            company,
            ids["actor_user"],
            "catalog." + entity,
            field,
            "read",
            version=version,
        )
        rejected = await client.get(root + path, headers=auth, params=params)
        assert rejected.status_code == 403, rejected.text


async def test_price_units_precision_and_series_cannot_be_rebound(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            item = await db.get(Item, ids["item"])
            assert item is not None
            other = Item(
                tenant_id=tenant_a,
                company_id=company,
                family_id=item.family_id,
                sku="OTHER",
                name="Other",
                base_unit_id=item.base_unit_id,
                sellable=True,
                purchasable=True,
            )
            pack = PackType(tenant_id=tenant_a, company_id=company, code="BOX", name="Box")
            db.add_all([other, pack])
            await db.flush()
            other_id, pack_id = other.id, pack.id
            purchase = await db.scalar(
                select(m.ItemPriceSeries).where(m.ItemPriceSeries.id != ids["item_price_series"])
            )
            assert purchase is not None
            purchase_id = purchase.id
            purchase_record = await db.scalar(
                select(m.ItemPriceDraft).where(m.ItemPriceDraft.series_id == purchase_id)
            )
            assert purchase_record is not None
            purchase_draft = purchase_record.id
    other_scope = await create(client, root, auth, "/price-scopes", {"item_id": str(other_id)})
    wrong_unit = await client.post(
        root + "/price-series",
        headers=command_headers(auth),
        json={
            "plan_id": str(ids["price_plan"]),
            "price_scope_id": other_scope["id"],
            "unit_revision_id": str(ids["item_unit_revision"]),
        },
    )
    assert wrong_unit.status_code == 403, wrong_unit.text
    async with changed(
        factory, tenant_a, ItemUnitRevision, ids["item_unit_revision"], pack_type_id=pack_id
    ):
        draft = await create(client, root, auth, "/price-drafts", draft_body(ids))
    changed_series = await client.put(
        root + "/price-drafts/" + draft["id"],
        headers=command_headers(auth),
        json=draft_body(ids, series_id=str(purchase_id), expected_version=1),
    )
    assert changed_series.status_code == 403, changed_series.text
    # A different currency's precision revision cannot be applied to the existing INR series.
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            number = m.ItemPriceNumericRevision(
                tenant_id=tenant_a,
                company_id=company,
                item_id=ids["item"],
                unit_revision_id=ids["item_unit_revision"],
                currency="USD",
                price_decimal_places=4,
                valid_from=dt.date(2090, 1, 1),
            )
            db.add(number)
            await db.flush()
            numeric_id = number.id
    response = await client.post(
        root + "/price-drafts",
        headers=command_headers(auth),
        json=draft_body(ids, numeric_revision_id=str(numeric_id)),
    )
    assert response.status_code == 403, response.text
    # Separate purchase authority also applies when looking through a draft's child.
    sale = headers(
        company,
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"purchase_price.read", "purchase_price.manage"}),
    )
    purchase_detail = await client.get(root + "/price-drafts/" + str(purchase_draft), headers=sale)
    assert purchase_detail.status_code == 403, purchase_detail.text
    async with changed(factory, tenant_a, m.PricePlan, ids["price_plan"], row_version=2**31 - 1):
        exhausted = await client.patch(
            root + "/price-plans/" + str(ids["price_plan"]),
            headers=command_headers(auth),
            json={"name": "Next", "expected_version": 2**31 - 1},
        )
        assert exhausted.status_code == 409, exhausted.text


async def test_purchase_capability_and_formula_authority_are_independent(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    with tenant_scope(tenant_a):
        async with factory() as db:
            plan = await db.scalar(select(m.PricePlan).where(m.PricePlan.purpose == "PURCHASE"))
            series = await db.scalar(
                select(m.ItemPriceSeries).where(m.ItemPriceSeries.id != ids["item_price_series"])
            )
            assert plan is not None and series is not None
            purchase_plan, purchase_series = plan.id, series.id
    async with changed(factory, tenant_a, Item, ids["item"], purchasable=False):
        for path, body in (
            ("/price-drafts", draft_body(ids, series_id=str(purchase_series))),
            ("/prices/resolve", query(ids, purpose="PURCHASE")),
        ):
            response = await client.post(root + path, headers=command_headers(auth), json=body)
            assert response.status_code == 409, response.text
    formula_body: dict[str, Any] = draft_body(
        ids,
        series_id=str(purchase_series),
        price_method="FORMULA",
        amount=None,
        formula={
            "recipe": "REFERENCE_COST_PLUS_MARKUP",
            "percentage": "10",
            "estimate_kind": "STANDARD_ESTIMATE",
            "rounding_mode": "UP",
        },
    )
    formula = await client.post(
        root + "/price-drafts", headers=command_headers(auth), json=formula_body
    )
    assert formula.status_code == 422, formula.text
    async with changed(
        factory,
        tenant_a,
        m.CompanyPricingPolicy,
        ids["company_pricing_policy"],
        purchase_plan_id=purchase_plan,
    ):
        missing = await client.post(
            root + "/prices/coverage", headers=auth, json=query(ids, purpose="PURCHASE")
        )
        assert missing.status_code == 200 and missing.json()["status"] == "MISSING", missing.text
