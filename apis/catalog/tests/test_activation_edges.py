import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    FamilyAttribute,
    Item,
    ItemVariantKey,
    Outbox,
    ProductFamily,
    ProductPricingPolicy,
)
from catalog.models.pricing import CompanyPricingPolicy, ItemMrp, ItemPrice, PriceLevel
from catalog.models.tax import ItemActivation, ItemInventoryProfile
from catalog.tasks import activation
from tests.product_review_factories import changed
from tests.tax_factories import DATE, seed_tax
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_pricing_levels_units import feature

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_service_activation_never_creates_inventory(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a, kind="SERVICE", treatment="EXEMPT")
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    route = root + "/items/" + str(ids["item"])
    preview = await client.post(
        route + "/activation-preview", headers=auth, json={"as_of": str(DATE)}
    )
    assert preview.status_code == 200 and preview.json()["eligible"], preview.text
    body = {
        key: preview.json()[key]
        for key in ("as_of", "expected_version", "expected_family_version", "preview_token")
    }
    result = await client.post(route + "/activate", headers=command_headers(auth), json=body)
    assert result.status_code == 200, result.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemInventoryProfile.id))) == 0


async def test_required_prices_pin_numeric_and_tier_sources(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    async with changed(
        factory,
        tenant_a,
        ProductPricingPolicy,
        ids["product_pricing_policy"],
        sale_price_mode="REQUIRED",
        mrp_mode="REQUIRED",
    ):
        result = await client.post(
            root + "/items/" + str(ids["item"]) + "/activation-preview",
            headers=auth,
            json={"as_of": str(DATE)},
        )
        assert result.status_code == 200 and result.json()["eligible"], result.text
        sources = {entry["entity_id"] for entry in result.json()["sources"]}
        assert {
            str(ids[key])
            for key in (
                "item_price",
                "item_price_series",
                "item_price_tier",
                "item_price_numeric_revision",
                "item_mrp",
            )
        } <= sources


async def test_activation_preview_invalidations_rollback_all_effects(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    route = root + "/items/" + str(ids["item"])
    result = await client.post(
        route + "/activation-preview", headers=auth, json={"as_of": str(DATE)}
    )
    assert result.status_code == 200 and result.json()["eligible"], result.text
    body = {
        key: result.json()[key]
        for key in ("as_of", "expected_version", "expected_family_version", "preview_token")
    }
    with tenant_scope(tenant_a):
        async with factory() as db:
            count = await db.scalar(select(func.count(Outbox.id)))
    for model, key, updates in (
        (ProductFamily, "product_family", {"row_version": 2}),
        (ItemVariantKey, "item_variant_key", {"row_version": 2}),
    ):
        async with changed(factory, tenant_a, model, ids[key], **updates):
            rejected = await client.post(
                route + "/activate", headers=command_headers(auth), json=body
            )
            assert rejected.status_code == 409, rejected.text
    denied = headers(company, tenant=tenant_a, user=ids["actor_user"], permission=["item.read"])
    for path in ("/activation-preview", "/activate"):
        for supplied, expected in (({}, 401), (denied, 403)):
            response = await client.post(
                route + path,
                headers=command_headers(supplied),
                json={"as_of": str(DATE)} if path.endswith("preview") else body,
            )
            assert response.status_code == expected, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Outbox.id))) == count
            assert await db.scalar(select(func.count(ItemActivation.id))) == 0
            item = await db.get(Item, ids["item"])
            assert item is not None and item.status == "DRAFT" and item.row_version == 1


async def test_activation_required_coverage_and_variant_gaps_are_explicit(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    await feature(factory, tenant_a, uuid.UUID(root.rsplit("/", 1)[1]), ids["actor_user"])
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    route = root + "/items/" + str(ids["item"]) + "/activation-preview"
    async with changed(
        factory,
        tenant_a,
        ProductPricingPolicy,
        ids["product_pricing_policy"],
        sale_price_mode="REQUIRED",
        mrp_mode="REQUIRED",
    ):
        cases: list[tuple[type[Any], str, dict[str, Any], str]] = [
            (
                CompanyPricingPolicy,
                "company_pricing_policy",
                {"valid_from": dt.date(2091, 1, 1)},
                "sale_pricing_policy",
            ),
            (ItemPrice, "item_price", {"valid_from": dt.date(2091, 1, 1)}, "price:"),
            (PriceLevel, "price_level", {"ordinal": 2}, "required_sale_levels"),
            (ItemMrp, "item_mrp", {"valid_from": dt.date(2091, 1, 1)}, "mrp:"),
            (
                ItemVariantKey,
                "item_variant_key",
                {"canonical_combination": b"changed"},
                "variant_identity",
            ),
            (FamilyAttribute, "family_attribute", {"is_axis": False}, "variant_axes"),
        ]
        for model, key, updates, missing in cases:
            async with changed(factory, tenant_a, model, ids[key], **updates):
                response = await client.post(route, headers=auth, json={"as_of": str(DATE)})
                assert response.status_code == 200, response.text
                assert any(x.startswith(missing) for x in response.json()["missing"]), response.text
