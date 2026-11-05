import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ItemUnitBinding, ItemUnitRevision
from catalog.models import pricing as m
from tests.pricing_factories import pack_unit
from tests.pricing_storage_factories import seed_pricing
from tests.product_review_factories import changed
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_pricing_resolution import query

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_missing_company_books_and_currency_coverage_are_distinct_from_invalid_selection(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    facts = (
        *all_facts(company, ids["actor_user"]),
        *(
            SnapshotRecord(
                kind="feature",
                id=uuid7(),
                data={
                    "company_id": str(company),
                    "feature_key": key,
                    "is_enabled": True,
                    "locked_at": None,
                },
            )
            for key in ("multi_price_levels", "multi_currency")
        ),
    )
    await setup_source(factory, tenant_a, company, ids["actor_user"], version=3, facts=facts)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            second = m.PriceLevel(
                tenant_id=tenant_a,
                company_id=company,
                code="PRICE2",
                name="Second",
                ordinal=2,
                is_active=True,
            )
            third = m.PriceLevel(
                tenant_id=tenant_a,
                company_id=company,
                code="PRICE3",
                name="Third",
                ordinal=3,
                is_active=True,
            )
            db.add_all([second, third])
            await db.flush()
            db.add(
                m.PricePlan(
                    tenant_id=tenant_a,
                    company_id=company,
                    code="EMPTY",
                    name="Empty",
                    purpose="SALE",
                    price_level_id=second.id,
                    currency="INR",
                    tax_basis="EXCLUSIVE",
                )
            )
            purchase = await db.scalar(select(m.PricePlan).where(m.PricePlan.purpose == "PURCHASE"))
            assert purchase is not None
            second_id, third_id, purchase_id = second.id, third.id, purchase.id

    async def missing(**values: Any) -> None:
        response = await client.post(
            root + "/prices/coverage", headers=auth, json=query(ids, **values)
        )
        assert response.status_code == 200 and response.json()["status"] == "MISSING", response.text

    async with changed(
        factory,
        tenant_a,
        m.CompanyPricingPolicy,
        ids["company_pricing_policy"],
        valid_from=dt.date(2091, 1, 1),
    ):
        await missing()
        rejected = await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
        assert rejected.status_code == 409, rejected.text
    await missing(price_level_id=str(third_id), override_reason="Administrative preview")
    mismatched = await client.post(
        root + "/prices/resolve",
        headers=auth,
        json=query(
            ids,
            plan_id=str(ids["price_plan"]),
            price_level_id=str(second_id),
            override_reason="Review",
        ),
    )
    assert mismatched.status_code == 422, mismatched.text
    async with changed(
        factory,
        tenant_a,
        m.CompanyPricingPolicy,
        ids["company_pricing_policy"],
        purchase_plan_id=purchase_id,
    ):
        await missing(purpose="PURCHASE", currency="USD")
    async with changed(
        factory, tenant_a, m.ItemPrice, ids["item_price"], valid_from=dt.date(2091, 1, 1)
    ):
        for fallback in (second_id, third_id):
            async with changed(
                factory,
                tenant_a,
                m.CompanyPricingPolicy,
                ids["company_pricing_policy"],
                missing_price_policy="FALLBACK",
                fallback_level_id=fallback,
            ):
                await missing()
        async with changed(
            factory,
            tenant_a,
            m.CompanyPricingPolicy,
            ids["company_pricing_policy"],
            sale_unit_mode="EXACT_BASE_DERIVATION",
        ):
            await missing()
    async with changed(factory, tenant_a, Item, ids["item"], sellable=False):
        rejected = await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
        assert rejected.status_code == 409, rejected.text


async def test_unit_derivation_requires_effective_base_and_actual_measurement(
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
            policy = await db.get(m.CompanyPricingPolicy, ids["company_pricing_policy"])
            assert item is not None and policy is not None
            policy.sale_unit_mode = "EXACT_BASE_DERIVATION"
            pack = await pack_unit(db, tenant_a, company)
            binding = ItemUnitBinding(
                tenant_id=tenant_a,
                company_id=company,
                item_id=item.id,
                unit_id=pack.id,
                code="CASE",
                usage_role="PACK",
            )
            db.add(binding)
            await db.flush()
            revision = ItemUnitRevision(
                tenant_id=tenant_a,
                company_id=company,
                binding_id=binding.id,
                revision=1,
                conversion_mode="FIXED",
                numerator=12,
                denominator=1,
                quantity_decimal_places=0,
                quantity_increment="1",
                fractional_entry=False,
                valid_from=dt.date(2090, 1, 1),
            )
            db.add(revision)
            await db.flush()
            revision_id = revision.id

    async def result(status: int, *, coverage: bool = False) -> dict[str, Any]:
        response = await client.post(
            root + ("/prices/coverage" if coverage else "/prices/resolve"),
            headers=auth,
            json=query(ids, unit_revision_id=str(revision_id)),
        )
        assert response.status_code == status, response.text
        return dict(response.json())

    assert (await result(200))["exact_consideration"] == {"numerator": "1200", "denominator": "1"}
    async with changed(
        factory,
        tenant_a,
        ItemUnitRevision,
        revision_id,
        conversion_mode="MEASURED",
        numerator=None,
        denominator=None,
        nominal_ratio="12",
        secondary_unit_id=item.base_unit_id,
    ):
        await result(409)
        async with changed(
            factory, tenant_a, m.ItemPrice, ids["item_price"], valid_from=dt.date(2091, 1, 1)
        ):
            assert (await result(200, coverage=True))["status"] == "MISSING"
    async with changed(
        factory,
        tenant_a,
        ItemUnitRevision,
        ids["item_unit_revision"],
        valid_from=dt.date(2091, 1, 1),
    ):
        await result(409, coverage=True)
