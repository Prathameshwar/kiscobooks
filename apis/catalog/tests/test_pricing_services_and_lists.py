import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.pricing_factories import create, foundation, publish_price, setup_pricing
from tests.test_commercial_api import command_headers
from tests.test_pricing_resolution import query, reference, resolve
from tests.test_product_authoring import create_product

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_service_hour_reference_cost_price_and_mrp_exclusion(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, product = await create_product(client, factory, tenant_a, service=True)
    root = f"/v1/companies/{company}"
    item = product["default_item"]["id"]
    binding = await client.post(
        root + f"/items/{item}/unit-bindings",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "code": "BASE",
            "unit_id": product["default_item"]["base_unit_id"],
            "role": "BASE",
            "numerator": 1,
            "denominator": 1,
            "quantity_decimal_places": 2,
            "quantity_increment": "0.25",
            "fractional_entry": True,
            "valid_from": "2090-01-01",
        },
    )
    assert binding.status_code == 200, binding.text
    bindings = await client.get(root + f"/items/{item}/unit-bindings", headers=auth)
    binding_id = bindings.json()["items"][0]["id"]
    revisions = await client.get(root + f"/item-unit-bindings/{binding_id}/revisions", headers=auth)
    assert revisions.status_code == 200, revisions.text
    ids = {
        "item": uuid.UUID(item),
        "item_unit_revision": uuid.UUID(revisions.json()["items"][0]["id"]),
        "actor_user": user,
    }
    setup = await foundation(client, root, auth, ids)
    cost = await create(
        client,
        root,
        auth,
        "/reference-costs",
        reference(ids, setup, setup["series"], amount="400", estimate_kind="SERVICE_ESTIMATE"),
    )
    mrp = await client.post(
        root + "/product-mrps",
        headers=command_headers(auth),
        json=reference(ids, setup, cost, jurisdiction="IN"),
    )
    assert mrp.status_code == 409, mrp.text
    await publish_price(
        client,
        root,
        auth,
        setup,
        price_method="FORMULA",
        amount=None,
        formula={
            "recipe": "REFERENCE_COST_TARGET_MARGIN",
            "percentage": "20",
            "estimate_kind": "SERVICE_ESTIMATE",
            "rounding_mode": "UP",
        },
    )
    result = await resolve(client, root, auth, ids, quantity="1.25")
    assert result["amount"] == "500.0000" and result["exact_consideration"] == {
        "numerator": "625",
        "denominator": "1",
    }
    below = await client.post(
        root + "/prices/resolve", headers=auth, json=query(ids, quantity="0.75")
    )
    assert below.status_code == 422, below.text
    off_grid = await client.post(
        root + "/prices/resolve", headers=auth, json=query(ids, quantity="1.10")
    )
    assert off_grid.status_code == 422, off_grid.text


async def test_pricing_list_allowlists_cursors_and_write_rate_limit(
    client: httpx.AsyncClient,
    app: FastAPI,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    for index in range(2):
        await create(
            client,
            root,
            auth,
            "/price-plans",
            {
                "code": f"REF{index}",
                "name": f"Reference {index}",
                "purpose": "REFERENCE_RETAIL",
                "currency": "INR",
                "tax_basis": "INCLUSIVE",
            },
        )
    first = await client.get(
        root + "/price-plans", headers=auth, params={"limit": 1, "sort": "-code"}
    )
    assert first.status_code == 200, first.text
    cursor = first.json()["page"]["next_cursor"]
    second = await client.get(
        root + "/price-plans", headers=auth, params={"limit": 1, "sort": "-code", "cursor": cursor}
    )
    assert second.status_code == 200, second.text
    assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]
    cases: list[tuple[str, dict[str, Any]]] = [
        ("price-plans", {"cursor": cursor, "sort": "code"}),
        ("price-plans", {"cursor": "forged"}),
        ("price-plans", {"as_of": "2090-01-01"}),
        ("price-plans", {"item_id": str(ids["item"])}),
        ("prices", {"q": "100"}),
        ("prices", {"sort": "amount"}),
        ("prices", {"offset": 100}),
        ("prices", {"limit": 201}),
    ]
    for path, params in cases:
        rejected = await client.get(root + "/" + path, headers=auth, params=params)
        assert rejected.status_code == 422, rejected.text
    filtered = await client.get(
        root + "/price-series", headers=auth, params={"plan_id": setup["plan"]["id"]}
    )
    assert filtered.status_code == 200 and len(filtered.json()["items"]) == 1
    bucket = tenant_a.hex + uuid.UUID(root.rsplit("/", 1)[1]).hex + ids["actor_user"].hex
    for _ in range(120):
        app.state.pricing_limiter.allow(bucket, limit=120)
    limited = await client.post(root + "/pricing/bootstrap", headers=command_headers(auth), json={})
    assert limited.status_code == 429 and set(limited.json()) == {"error"}, limited.text
