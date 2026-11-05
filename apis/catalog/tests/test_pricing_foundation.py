import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.pricing_factories import foundation, setup_pricing
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_pricing_foundation_and_scoped_history(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    result = await foundation(client, root, auth, ids)
    for path, key in (
        ("price-levels", "level"),
        ("price-plans", "plan"),
        ("company-pricing-policies", "policy"),
        ("price-scopes", "scope"),
        ("price-numeric-revisions", "numeric"),
        ("price-series", "series"),
    ):
        detail = await client.get(root + f"/{path}/" + result[key]["id"], headers=auth)
        assert detail.status_code == 200, detail.text
        page = await client.get(root + f"/{path}", headers=auth, params={"limit": 1})
        assert page.status_code == 200, page.text
        assert page.json()["items"][0]["id"] == result[key]["id"]
    receipt = command_headers(auth)
    body = {"expected_version": 1, "name": "Retail", "is_active": True}
    url = root + "/price-levels/" + result["level"]["id"]
    updated = await client.patch(url, headers=receipt, json=body)
    assert updated.status_code == 200, updated.text
    replay = await client.patch(url, headers=receipt, json=body)
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["row_version"] == 2
    assert (
        await client.get(
            root + "/price-levels", headers=auth, params={"sort": "code,id", "q": "PRICE"}
        )
    ).status_code == 200
