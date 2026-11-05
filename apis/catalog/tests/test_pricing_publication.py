import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.pricing_factories import create, foundation, guard, publish_price, setup_pricing
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_fixed_price_publication_retains_history(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    draft, price = await publish_price(
        client, root, auth, setup, amount="0.1234", price_basis_quantity="1000"
    )
    detail = await client.get(root + "/prices/" + price["id"], headers=auth)
    assert detail.status_code == 200, detail.text
    assert detail.json()["amount"] == "0.1234"
    assert detail.json()["price_basis_quantity"] == "1000.0000"
    later = await create(
        client,
        root,
        auth,
        "/price-drafts",
        {
            "series_id": setup["series"]["id"],
            "numeric_revision_id": setup["numeric"]["id"],
            "valid_from": "2091-01-01",
            "price_method": "FIXED",
            "amount": "0.2345",
            "price_basis_quantity": "1000",
        },
    )
    body = {
        **guard(later),
        "expected_version": 1,
        "supersedes_id": price["id"],
        "expected_previous_version": 1,
    }
    receipt = command_headers(auth)
    response = await client.post(
        root + "/price-drafts/" + later["id"] + "/publish", headers=receipt, json=body
    )
    assert response.status_code == 201, response.text
    replay = await client.post(
        root + "/price-drafts/" + later["id"] + "/publish", headers=receipt, json=body
    )
    assert replay.headers["Idempotency-Replayed"] == "true"
    old = await client.get(root + "/prices/" + price["id"], headers=auth)
    assert old.json()["amount"] == "0.1234" and old.json()["valid_to"] == "2090-12-31"
    assert (
        await client.get(root + "/prices", headers=auth, params={"as_of": "2091-01-01"})
    ).json()["items"][0]["id"] == response.json()["id"]
    reject = await client.post(
        root + "/price-drafts/" + draft["id"] + "/publish",
        headers=command_headers(auth),
        json={**guard(response.json()), "expected_version": 2},
    )
    assert reject.status_code == 409, reject.text


async def test_purchase_gross_and_net_reference_terms(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids, purpose="PURCHASE")
    _, price = await publish_price(
        client,
        root,
        auth,
        setup,
        amount="72",
        purchase_term={"gross_amount": "80", "discount_kind": "PERCENT", "discount_value": "10"},
    )
    terms = await client.get(
        root + "/purchase-price-terms", headers=auth, params={"price_id": price["id"]}
    )
    assert terms.status_code == 200, terms.text
    assert terms.json()["items"][0]["gross_amount"] == "80.0000"
