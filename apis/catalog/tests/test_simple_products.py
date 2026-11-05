"""Product facade reuses native persistence and protects both aggregate owners."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import func, select

from catalog.models import Item, Outbox, ProductFamily
from tests.product_factories import setup_product
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def simple_input(body):
    return {
        "authoring_version": 0,
        "code": body["default_item"]["sku"],
        "name": body["name"],
        "kind": body["kind"],
        "product_type_revision_id": body["product_type_revision_id"],
        "base_unit_id": body["default_item"]["base_unit_id"],
        "min_sale_quantity": "1",
    }


async def create_simple(client, factory, tenant):
    company, user, auth, legacy = await setup_product(factory, tenant, advanced=False)
    route = f"/v1/companies/{company}/products"
    body = simple_input(legacy)
    response = await client.post(route, headers=command_headers(auth), json=body)
    assert response.status_code == 201, response.text
    return company, user, auth, body, response.json()


@pytest.mark.parametrize("kind", ["GOODS", "SERVICE"])
async def test_simple_create_read_edit_and_replay(client, factory, tenant_a, kind):
    company, _, auth, legacy = await setup_product(factory, tenant_a, kind=kind, advanced=False)
    route = f"/v1/companies/{company}/products"
    body = simple_input(legacy)
    receipt = command_headers(auth)
    response = await client.post(route, headers=receipt, json=body)
    assert response.status_code == 201, response.text
    product = response.json()
    assert product["code"] == "SKU1" and product["name"] == "Product"
    assert "family" not in product and "default_item" not in product
    assert response.headers["Location"].endswith(product["id"])
    replay = await client.post(route, headers=receipt, json=body)
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == product["id"]
    assert replay.headers["Idempotency-Replayed"] == "true"
    listing = await client.get(route, headers=auth, params={"sort": "code"})
    assert listing.status_code == 200, listing.text
    assert listing.json()["items"][0]["id"] == product["id"]
    assert "description" not in listing.json()["items"][0]
    detail = await client.get(route + "/" + product["id"], headers=auth)
    assert detail.status_code == 200, detail.text
    patch = {
        "authoring_version": 0,
        "revision": detail.json()["revision"],
        "name": "Renamed product",
        "description": "One product edit",
    }
    changed = await client.patch(
        route + "/" + product["id"], headers=command_headers(auth), json=patch
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["name"] == "Renamed product"
    stale = await client.patch(
        route + "/" + product["id"], headers=command_headers(auth), json=patch
    )
    assert stale.status_code == 409, stale.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductFamily.id))) == 1
            assert await db.scalar(select(func.count(Item.id))) == 1
            item = await db.get(Item, uuid.UUID(product["id"]))
            family = await db.get(ProductFamily, item.family_id)
            assert family.name == item.name == "Renamed product"
            assert family.code.startswith("P") and len(family.code) <= 30


async def test_simple_failure_rolls_back_and_legacy_remains_available(client, factory, tenant_a):
    company, _, auth, legacy = await setup_product(factory, tenant_a, advanced=False)
    route = f"/v1/companies/{company}/products"
    bad = {**simple_input(legacy), "base_unit_id": str(uuid.uuid4())}
    response = await client.post(route, headers=command_headers(auth), json=bad)
    assert response.status_code in {404, 422}, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 0
            assert await db.scalar(select(func.count(ProductFamily.id))) == 0
            assert await db.scalar(select(func.count(Outbox.id))) == 0
    old = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=legacy
    )
    assert old.status_code == 201, old.text
    product = await client.get(route + "/" + old.json()["default_item"]["id"], headers=auth)
    assert product.status_code == 200, product.text
    assert product.json()["name"] == legacy["default_item"]["name"]


async def test_product_revision_is_bound_to_owner_and_actor(client, factory, tenant_a):
    company, _, auth, body, first = await create_simple(client, factory, tenant_a)
    route = f"/v1/companies/{company}/products"
    second = await client.post(
        route, headers=command_headers(auth), json={**body, "code": "SECOND"}
    )
    assert second.status_code == 201, second.text
    changed = await client.patch(
        route + "/" + second.json()["id"],
        headers=command_headers(auth),
        json={"authoring_version": 0, "revision": first["revision"], "name": "Wrong owner"},
    )
    assert changed.status_code == 422, changed.text
