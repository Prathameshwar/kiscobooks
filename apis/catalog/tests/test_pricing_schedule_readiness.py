"""Known dated coverage and publication-history conflicts must be reviewable."""

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ItemUnitBinding, ItemUnitRevision, ProductPricingPolicy
from catalog.tasks import activation
from tests.pricing_factories import create, foundation, guard, publish_price, setup_pricing
from tests.tax_factories import seed_tax
from tests.test_commercial_api import command_headers
from tests.test_pricing_readiness import draft_body
from tests.test_pricing_resolution import reference

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def preview(
    client: httpx.AsyncClient, root: str, auth: dict[str, str], draft: dict[str, Any]
) -> dict[str, Any]:
    response = await client.get(root + "/price-drafts/" + draft["id"] + "/preview", headers=auth)
    assert response.status_code == 200, response.text
    return dict(response.json())


async def test_live_formula_cannot_outlive_known_source_coverage(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    await create(
        client,
        root,
        auth,
        "/reference-costs",
        reference(
            ids,
            setup,
            setup["series"],
            estimate_kind="STANDARD_ESTIMATE",
            valid_to="2090-01-31",
        ),
    )
    body = draft_body(
        setup,
        price_method="FORMULA",
        amount=None,
        formula={
            "recipe": "REFERENCE_COST_PLUS_MARKUP",
            "percentage": "25",
            "estimate_kind": "STANDARD_ESTIMATE",
            "rounding_mode": "HALF_UP",
        },
    )
    draft = await create(client, root, auth, "/price-drafts", body)
    result = await preview(client, root, auth, draft)
    assert result["valid"] is False and result["coverage_valid_to"] == "2090-01-31", result
    assert any(issue["code"] == "SOURCE_COVERAGE_GAP" for issue in result["issues"])
    rejected = await client.post(
        root + "/price-drafts/" + draft["id"] + "/publish",
        headers=command_headers(auth),
        json={**guard(result), "expected_version": 1},
    )
    assert rejected.status_code == 409, rejected.text
    # Explicitly limiting the price to its source coverage is valid.
    replaced = await client.put(
        root + "/price-drafts/" + draft["id"],
        headers=command_headers(auth),
        json={**body, "expected_version": 1, "valid_to": "2090-01-31"},
    )
    assert replaced.status_code == 200, replaced.text
    result = await preview(client, root, auth, draft)
    assert result["valid"] and result["publishable"], result
    await create(
        client,
        root,
        auth,
        "/price-drafts/" + draft["id"] + "/publish",
        {**guard(result), "expected_version": 2},
    )


async def test_contiguous_source_revisions_cover_a_live_formula(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    source = await create(
        client,
        root,
        auth,
        "/reference-costs",
        reference(
            ids,
            setup,
            setup["series"],
            estimate_kind="STANDARD_ESTIMATE",
            valid_to="2090-01-31",
        ),
    )
    later = await create(
        client,
        root,
        auth,
        "/reference-costs",
        reference(
            ids,
            setup,
            source,
            estimate_kind="STANDARD_ESTIMATE",
            valid_from="2090-02-01",
            amount="88",
        ),
    )
    draft = await create(
        client,
        root,
        auth,
        "/price-drafts",
        draft_body(
            setup,
            price_method="FORMULA",
            amount=None,
            formula={
                "recipe": "REFERENCE_COST_PLUS_MARKUP",
                "percentage": "25",
                "estimate_kind": "STANDARD_ESTIMATE",
                "rounding_mode": "HALF_UP",
            },
        ),
    )
    result = await preview(client, root, auth, draft)
    assert result["valid"] and result["coverage_valid_to"] is None, result
    assert {source["id"], later["id"]} <= set(result["source_ids"])


async def test_preview_reports_same_date_conflict_and_forward_predecessor(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    _, published = await publish_price(client, root, auth, setup)
    draft = await create(client, root, auth, "/price-drafts", draft_body(setup, amount="110"))
    result = await preview(client, root, auth, draft)
    assert result["valid"] and result["publishable"] is False, result
    assert any(issue["code"] == "HISTORY_CONFLICT" for issue in result["publication_issues"])
    changed = await client.put(
        root + "/price-drafts/" + draft["id"],
        headers=command_headers(auth),
        json={**draft_body(setup, amount="110", valid_from="2091-01-01"), "expected_version": 1},
    )
    assert changed.status_code == 200, changed.text
    result = await preview(client, root, auth, draft)
    assert result["valid"] and result["publishable"], result
    assert result["supersedes_id"] == published["id"] and result["expected_previous_version"] == 1


async def test_published_draft_is_readable_but_not_publishable_again(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    draft, _ = await publish_price(client, root, auth, setup)
    result = await preview(client, root, auth, draft)
    assert result["valid"] and result["publishable"] is False, result
    assert result["publication_issues"][0]["code"] == "ALREADY_PUBLISHED"


async def test_activation_requires_prices_for_scheduled_unit_revisions(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            pricing = await db.get(ProductPricingPolicy, ids["product_pricing_policy"])
            binding = await db.get(ItemUnitBinding, ids["item_unit_binding"])
            assert pricing is not None and binding is not None
            pricing.sale_price_mode = "REQUIRED"
            unit_id, binding_id, code = str(binding.unit_id), str(binding.id), binding.code
    revised = await client.post(
        root + f"/items/{ids['item']}/unit-revisions",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "binding_id": binding_id,
            "code": code,
            "unit_id": unit_id,
            "role": "BASE",
            "conversion_mode": "FIXED",
            "numerator": "1",
            "denominator": "1",
            "quantity_decimal_places": 0,
            "quantity_increment": "1",
            "fractional_entry": False,
            "valid_from": "2091-01-01",
        },
    )
    assert revised.status_code == 200, revised.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            revision = await db.scalar(
                select(ItemUnitRevision).where(
                    ItemUnitRevision.binding_id == uuid.UUID(binding_id),
                    ItemUnitRevision.revision == 2,
                )
            )
            assert revision is not None
            revision_id = str(revision.id)
    path = root + f"/items/{ids['item']}/activation-preview"
    result = await client.post(path, headers=auth, json={"as_of": "2090-01-01"})
    assert result.status_code == 200, result.text
    assert result.json()["eligible"] is False, result.text
    assert any(revision_id in issue for issue in result.json()["missing"])
    numeric = await create(
        client,
        root,
        auth,
        "/price-numeric-revisions",
        {
            "expected_generation": revised.json()["policy_generation"],
            "expected_source_version": 2,
            "item_id": str(ids["item"]),
            "unit_revision_id": revision_id,
            "currency": "INR",
            "price_decimal_places": 4,
            "valid_from": "2091-01-01",
        },
    )
    series = await create(
        client,
        root,
        auth,
        "/price-series",
        {
            "plan_id": str(ids["price_plan"]),
            "price_scope_id": str(ids["item_price_scope"]),
            "unit_revision_id": revision_id,
        },
    )
    _, published = await publish_price(
        client, root, auth, {"numeric": numeric, "series": series}, valid_from="2091-01-01"
    )
    result = await client.post(path, headers=auth, json={"as_of": "2090-01-01"})
    assert result.status_code == 200 and result.json()["eligible"], result.text
    assert published["id"] in {source["entity_id"] for source in result.json()["sources"]}
