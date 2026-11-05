import datetime as dt
import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.gateway import decode_actor_context
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ItemUnitBinding, ItemUnitRevision, ProductPricingPolicy, UnitOfMeasure
from catalog.models.pricing import (
    CompanyPricingPolicy,
    ItemPriceDraft,
    ItemPriceSeries,
    PriceLevel,
    PricePlan,
)
from catalog.tasks import activation
from catalog.tasks.activation_prices import coverage
from catalog.tasks.product_requirements import product_work
from catalog.tasks.tax_resolution import Pins
from tests.conftest import ACTOR_SECRET
from tests.product_review_factories import changed
from tests.tax_factories import DATE, seed_tax
from tests.test_commercial_api import command_headers
from tests.test_pricing_levels_units import feature

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_required_purchase_reference_and_unit_roles_preserve_sources(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            plan = await db.scalar(select(PricePlan).where(PricePlan.purpose == "PURCHASE"))
            assert plan is not None
            purchase_id = plan.id
            draft = await db.scalar(
                select(ItemPriceDraft)
                .join(ItemPriceSeries, ItemPriceDraft.series_id == ItemPriceSeries.id)
                .where(ItemPriceSeries.plan_id == purchase_id)
            )
            assert draft is not None
            draft_id = draft.id
            policy = await db.get(CompanyPricingPolicy, ids["company_pricing_policy"])
            assert policy is not None
            policy.purchase_plan_id = purchase_id
    published = await client.post(
        root + "/price-drafts/" + str(draft_id) + "/publish",
        headers=command_headers(auth),
        json={"expected_version": 1, "expected_generation": 1, "expected_source_version": 2},
    )
    assert published.status_code == 201, published.text
    route = root + "/items/" + str(ids["item"]) + "/activation-preview"
    async with changed(
        factory,
        tenant_a,
        ProductPricingPolicy,
        ids["product_pricing_policy"],
        purchase_reference_mode="REQUIRED",
        sale_price_mode="REQUIRED",
        mrp_mode="REQUIRED",
    ):
        result = await client.post(route, headers=auth, json={"as_of": str(DATE)})
        assert result.status_code == 200 and result.json()["eligible"], result.text
        assert "catalog.purchase_price_term" in {x["entity_type"] for x in result.json()["sources"]}
        async with (
            changed(
                factory,
                tenant_a,
                UnitOfMeasure,
                ids["unit_of_measure"],
                decimal_places=1,
                quantity_increment=Decimal("0.5"),
            ),
            changed(
                factory,
                tenant_a,
                ItemUnitRevision,
                ids["item_unit_revision"],
                quantity_decimal_places=1,
                quantity_increment=Decimal("0.5"),
                fractional_entry=False,
            ),
        ):
            result = await client.post(route, headers=auth, json={"as_of": str(DATE)})
            assert result.status_code == 200 and result.json()["eligible"], result.text
        async with changed(
            factory,
            tenant_a,
            CompanyPricingPolicy,
            ids["company_pricing_policy"],
            purchase_plan_id=ids["price_plan"],
        ):
            result = await client.post(route, headers=auth, json={"as_of": str(DATE)})
            assert (
                result.status_code == 200 and "purchase_book" in result.json()["missing"]
            ), result.text
        for role in ("SALE", "PURCHASE"):
            async with changed(
                factory, tenant_a, ItemUnitBinding, ids["item_unit_binding"], usage_role=role
            ):
                result = await client.post(route, headers=auth, json={"as_of": str(DATE)})
                assert (
                    result.status_code == 200 and "base_unit_binding" in result.json()["missing"]
                ), result.text


async def test_every_configured_sale_level_needs_its_currency_book(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await feature(factory, tenant_a, company, ids["actor_user"])
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                PriceLevel(
                    tenant_id=tenant_a,
                    company_id=company,
                    code="PRICE2",
                    name="Trade",
                    ordinal=2,
                    is_active=True,
                )
            )
    async with changed(
        factory,
        tenant_a,
        ProductPricingPolicy,
        ids["product_pricing_policy"],
        sale_price_mode="REQUIRED",
        sale_level_count=2,
    ):
        result = await client.post(
            root + "/items/" + str(ids["item"]) + "/activation-preview",
            headers=auth,
            json={"as_of": str(DATE)},
        )
        assert result.status_code == 200, result.text
        assert any(entry.startswith("sale_book:") for entry in result.json()["missing"])


async def test_price_coverage_rejects_physical_mrp_for_service_configuration(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a, kind="SERVICE")
    company = uuid.UUID(root.rsplit("/", 1)[1])
    actor = decode_actor_context(
        auth["x-actor-context"], auth["x-actor-signature"], ACTOR_SECRET.encode()
    )
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    with tenant_scope(tenant_a):
        async with factory() as db:
            work = await product_work(db, actor, company, ids["item"])
            _, config = await activation.prepare(work, DATE, ACTOR_SECRET.encode())
            invalid = config.model_copy(
                update={"pricing": config.pricing.model_copy(update={"mrp_mode": "REQUIRED"})}
            )
            with pytest.raises(ConflictError, match="MRP"):
                await coverage(work, invalid, DATE, Pins())
