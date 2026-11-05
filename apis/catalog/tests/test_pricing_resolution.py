import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.pricing_factories import create, foundation, guard, publish_price, setup_pricing
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def query(ids: dict[str, uuid.UUID], **values: Any) -> dict[str, Any]:
    return {
        "item_id": str(ids["item"]),
        "unit_revision_id": str(ids["item_unit_revision"]),
        "currency": "INR",
        "as_of": "2090-01-01",
        "quantity": "1",
        **values,
    }


def reference(
    ids: dict[str, uuid.UUID], setup: dict[str, Any], token: dict[str, Any], **values: Any
) -> dict[str, Any]:
    return {
        **guard(token),
        "item_id": str(ids["item"]),
        "unit_revision_id": str(ids["item_unit_revision"]),
        "numeric_revision_id": setup["numeric"]["id"],
        "currency": "INR",
        "valid_from": "2090-01-01",
        "amount": "80",
        "price_basis_quantity": "1",
        "source_reference": "Reviewed reference",
        **values,
    }


async def resolve(
    client: httpx.AsyncClient,
    root: str,
    auth: dict[str, str],
    ids: dict[str, uuid.UUID],
    **values: Any,
) -> dict[str, Any]:
    response = await client.post(root + "/prices/resolve", headers=auth, json=query(ids, **values))
    assert response.status_code == 200, response.text
    return dict(response.json())


async def test_regular_price_resolution_uses_exact_per_n_and_volume_quantity(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    missing = await client.post(root + "/prices/coverage", headers=auth, json=query(ids))
    assert missing.status_code == 200 and missing.json()["status"] == "MISSING", missing.text
    assert (
        await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
    ).status_code == 409
    _, published = await publish_price(
        client,
        root,
        auth,
        setup,
        price_method="TIERS",
        amount=None,
        price_basis_quantity="1000",
        tiers=[
            {"min_quantity": "0", "max_quantity": "10", "amount": "0.1234"},
            {"min_quantity": "10", "amount": "0.1000"},
        ],
    )
    result = await resolve(client, root, auth, ids, quantity="10")
    assert result["amount"] == "0.1000" and result["exact_consideration"] == {
        "numerator": "1",
        "denominator": "1000",
    }
    assert result["price_id"] == published["id"] and result["tier_id"] is not None
    assert result["final_guard_validation_required"] is True
    assert (await resolve(client, root, auth, ids, quantity="9"))["amount"] == "0.1234"


async def test_sale_channel_price_precedes_generic_and_other_channels_fall_back(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    _, generic = await publish_price(client, root, auth, setup, amount="100")
    channels = {}
    for code in ("STORE", "WHOLESALE", "MARKETPLACE"):
        channels[code] = await create(
            client, root, auth, "/sales-channels", {"code": code, "name": code}
        )
    channel_series = await create(
        client,
        root,
        auth,
        "/price-series",
        {
            "plan_id": setup["plan"]["id"],
            "price_scope_id": setup["scope"]["id"],
            "unit_revision_id": str(ids["item_unit_revision"]),
            "channel_code": "STORE",
        },
    )
    _, store_price = await publish_price(
        client, root, auth, {**setup, "series": channel_series}, amount="90"
    )
    ordinary = await resolve(client, root, auth, ids)
    assert ordinary["price_id"] == generic["id"]
    assert ordinary["selected_channel_code"] is None
    store = await resolve(client, root, auth, ids, channel_code="STORE")
    assert store["price_id"] == store_price["id"]
    assert store["requested_channel_code"] == store["selected_channel_code"] == "STORE"
    wholesale_series = await create(
        client,
        root,
        auth,
        "/price-series",
        {
            "plan_id": setup["plan"]["id"],
            "price_scope_id": setup["scope"]["id"],
            "unit_revision_id": str(ids["item_unit_revision"]),
            "channel_code": "WHOLESALE",
        },
    )
    _, wholesale_price = await publish_price(
        client, root, auth, {**setup, "series": wholesale_series}, amount="80"
    )
    wholesale = await resolve(client, root, auth, ids, channel_code="WHOLESALE")
    assert wholesale["price_id"] == wholesale_price["id"]
    assert wholesale["selected_channel_code"] == "WHOLESALE"
    marketplace = await resolve(client, root, auth, ids, channel_code="MARKETPLACE")
    assert marketplace["price_id"] == generic["id"]
    assert marketplace["selected_channel_code"] is None
    duplicate = await client.post(
        root + "/price-series",
        headers=command_headers(auth),
        json={
            "plan_id": setup["plan"]["id"],
            "price_scope_id": setup["scope"]["id"],
            "unit_revision_id": str(ids["item_unit_revision"]),
            "channel_code": "STORE",
        },
    )
    assert duplicate.status_code == 409, duplicate.text
    store_channel = channels["STORE"]
    blocked_retirement = await client.post(
        root + f"/sales-channels/{store_channel['id']}/deactivate",
        headers=command_headers(auth),
        json={"expected_version": store_channel["row_version"]},
    )
    assert blocked_retirement.status_code == 409, blocked_retirement.text
    blocked_rename = await client.patch(
        root + f"/sales-channels/{store_channel['id']}",
        headers=command_headers(auth),
        json={"expected_version": store_channel["row_version"], "code": "STORE_NEW"},
    )
    assert blocked_rename.status_code == 409, blocked_rename.text


async def test_live_estimate_recipe_and_floor_retain_sources(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    cost = await create(
        client,
        root,
        auth,
        "/reference-costs",
        reference(ids, setup, setup["series"], estimate_kind="STANDARD_ESTIMATE"),
    )
    floor = await create(
        client,
        root,
        auth,
        "/commercial-guard-rules",
        reference(
            ids,
            setup,
            cost,
            rule_kind="MIN_MARKUP",
            amount=None,
            percentage="20",
            estimate_kind="STANDARD_ESTIMATE",
        ),
    )
    scope = await create(client, root, auth, "/commercial-policy-scopes", {"owner_kind": "COMPANY"})
    discount = await create(
        client,
        root,
        auth,
        "/discount-ceilings",
        {
            **guard(scope),
            "scope_id": scope["id"],
            "valid_from": "2090-01-01",
            "max_discount_pct": "10",
        },
    )
    _, published = await publish_price(
        client,
        root,
        auth,
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
    result = await resolve(client, root, auth, ids)
    assert result["amount"] == "100.0000", result
    assert result["minimum_rate"] == {"numerator": "96", "denominator": "1"}
    assert cost["id"] in result["source_ids"] and floor["id"] in result["guard_ids"]
    assert discount["id"] in result["guard_ids"] and result["max_discount_pct"] == "10.0000"
    cost2 = await create(
        client,
        root,
        auth,
        "/reference-costs",
        reference(
            ids,
            setup,
            published,
            valid_from="2091-01-01",
            amount="88",
            estimate_kind="STANDARD_ESTIMATE",
            supersedes_id=cost["id"],
            expected_previous_version=1,
        ),
    )
    future = await resolve(client, root, auth, ids, as_of="2091-01-01")
    assert future["amount"] == "110.0000" and cost2["id"] in future["source_ids"]
    assert (await resolve(client, root, auth, ids))["amount"] == "100.0000"


async def test_mrp_recipe_and_tax_basis_fail_closed(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids, tax_basis="INCLUSIVE")
    mrp = await create(
        client,
        root,
        auth,
        "/product-mrps",
        reference(ids, setup, setup["series"], amount="100", jurisdiction="IN"),
    )
    _, published = await publish_price(
        client,
        root,
        auth,
        setup,
        price_method="FORMULA",
        amount=None,
        formula={
            "recipe": "MRP_LESS_PERCENT",
            "percentage": "10",
            "jurisdiction": "IN",
            "rounding_mode": "DOWN",
        },
    )
    result = await resolve(client, root, auth, ids, jurisdiction="IN")
    assert result["amount"] == "90.0000" and mrp["id"] in result["source_ids"]
    await create(
        client,
        root,
        auth,
        "/commercial-guard-rules",
        reference(ids, setup, published, rule_kind="FIXED_MIN", amount="50"),
    )
    incomplete = await resolve(client, root, auth, ids, jurisdiction="IN")
    assert (
        incomplete["status"] == "NEEDS_TAX_CONTEXT"
        and incomplete["amount"] is None
        and incomplete["exact_consideration"] is None
    )


async def test_purchase_resolution_reports_reference_terms(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids, purpose="PURCHASE")
    await publish_price(
        client,
        root,
        auth,
        setup,
        amount="72",
        purchase_term={
            "gross_amount": "80",
            "discount_kind": "FIXED_PER_BASIS",
            "discount_value": "8",
        },
    )
    result = await resolve(client, root, auth, ids, purpose="PURCHASE", quantity="100")
    assert result["exact_consideration"] == {"numerator": "7200", "denominator": "1"}
    assert result["purchase_term"]["gross_amount"] == "80.0000"
