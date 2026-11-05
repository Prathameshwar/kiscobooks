import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, Outbox, ProductFamily
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("kind", ["GOODS", "SERVICE"])
async def test_simple_product_roundtrip(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    kind: str,
) -> None:
    company, _, current, body = await setup_product(factory, tenant_a, kind=kind)
    route = f"/v1/companies/{company}/product-families"
    receipt = command_headers(current)
    created = await client.post(route, headers=receipt, json=body)
    assert created.status_code == 201, created.text
    data = created.json()
    family = data["family"]
    item = data["default_item"]
    assert created.headers["Location"].endswith(family["id"])
    assert family["status"] == item["status"] == "DRAFT"
    assert item["family_id"] == family["id"]
    assert (await client.post(route, headers=receipt, json=body)).headers[
        "Idempotency-Replayed"
    ] == "true"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductFamily.id))) == 1
            assert await db.scalar(select(func.count(Item.id))) == 1
            row = await db.get(Item, uuid.UUID(item["id"]))
            assert row is not None and isinstance(row.min_sale_quantity, Decimal)
            assert (
                await db.scalar(select(func.count(Outbox.id)).where(Outbox.tenant_id == tenant_a))
                == 2
            )
    for path, record in ((route, family), (f"/v1/companies/{company}/items", item)):
        assert (await client.get(path + "/" + record["id"], headers=current)).status_code == 200
        changed = await client.patch(
            path + "/" + record["id"],
            headers=command_headers(current),
            json={"expected_version": 1, "name": "New name"},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["row_version"] == 2
        noop = await client.patch(
            path + "/" + record["id"],
            headers=command_headers(current),
            json={"expected_version": 2, "name": "New name"},
        )
        assert noop.status_code == 200 and noop.json()["row_version"] == 2
        stale = await client.patch(
            path + "/" + record["id"],
            headers=command_headers(current),
            json={"expected_version": 1, "name": "Stale"},
        )
        assert stale.status_code == 409
    second = {**body, "code": "PRODUCT2", "default_item": {**body["default_item"], "sku": "SKU2"}}
    second_created = await client.post(route, headers=command_headers(current), json=second)
    assert second_created.status_code == 201
    second_item_id = second_created.json()["default_item"]["id"]
    for path, sort in ((route, "code"), (f"/v1/companies/{company}/items", "sku")):
        first = await client.get(path, headers=current, params={"limit": 1, "sort": sort})
        assert first.status_code == 200, first.text
        assert "custom_fields" not in first.json()["items"][0]
        assert "description" not in first.json()["items"][0]
        next_page = await client.get(
            path,
            headers=current,
            params={"limit": 1, "sort": sort, "cursor": first.json()["page"]["next_cursor"]},
        )
        assert next_page.status_code == 200, next_page.text
        assert next_page.json()["items"][0]["id"] != first.json()["items"][0]["id"]
        assert (
            await client.get(path, headers=current, params={"q": "New", "sort": "-name"})
        ).status_code == 200
        assert (
            await client.get(path, headers=current, params={"sort": "description"})
        ).status_code == 422
    matched = await client.get(
        f"/v1/companies/{company}/items",
        headers=current,
        params={"family_id": family["id"], "sellable": "true"},
    )
    assert [x["id"] for x in matched.json()["items"]] == [item["id"]]
    by_unit = await client.get(
        f"/v1/companies/{company}/items",
        headers=current,
        params={"base_unit_id": item["base_unit_id"], "status": "DRAFT", "sort": "sku", "limit": 1},
    )
    assert by_unit.status_code == 200, by_unit.text
    assert by_unit.json()["page"]["has_more"]
    next_unit = await client.get(
        f"/v1/companies/{company}/items",
        headers=current,
        params={
            "base_unit_id": item["base_unit_id"],
            "status": "DRAFT",
            "sort": "sku",
            "limit": 1,
            "cursor": by_unit.json()["page"]["next_cursor"],
        },
    )
    assert next_unit.status_code == 200, next_unit.text
    assert {by_unit.json()["items"][0]["id"], next_unit.json()["items"][0]["id"]} == {
        item["id"],
        second_item_id,
    }
    changed_unit_filter = await client.get(
        f"/v1/companies/{company}/items",
        headers=current,
        params={
            "status": "DRAFT",
            "sort": "sku",
            "limit": 1,
            "cursor": by_unit.json()["page"]["next_cursor"],
        },
    )
    assert changed_unit_filter.status_code == 422


async def test_product_scope_validation_and_rollback(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, current, body = await setup_product(factory, tenant_a)
    other, _, foreign_auth, foreign = await setup_product(factory, tenant_a)
    route = f"/v1/companies/{company}/product-families"
    cases = [
        ({**body, "product_type_revision_id": foreign["product_type_revision_id"]}, 403),
        ({**body, "kind": "SERVICE"}, 409),
        (
            {
                **body,
                "default_item": {
                    **body["default_item"],
                    "base_unit_id": foreign["default_item"]["base_unit_id"],
                },
            },
            403,
        ),
        ({**body, "default_item": {**body["default_item"], "min_sale_quantity": "0.5"}}, 422),
        ({**body, "opening_stock": "12"}, 422),
        ({**body, "default_item": {**body["default_item"], "on_hand": "12"}}, 422),
    ]
    for invalid, status in cases:
        response = await client.post(route, headers=command_headers(current), json=invalid)
        assert response.status_code == status, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductFamily.id))) == 0
            assert (
                await db.scalar(select(func.count(Outbox.id)).where(Outbox.tenant_id == tenant_a))
                == 0
            )
    created = await client.post(route, headers=command_headers(current), json=body)
    assert created.status_code == 201, created.text
    data = created.json()
    object_id = data["family"]["id"]
    duplicate = {**body, "code": "OTHER"}
    assert (
        await client.post(route, headers=command_headers(current), json=duplicate)
    ).status_code == 409
    assert (
        await client.get(
            f"/v1/companies/{other}/product-families/{object_id}", headers=foreign_auth
        )
    ).status_code == 403
    denied = headers(company, tenant=tenant_a, user=user, permission=["item.read"])
    assert (await client.post(route, headers=command_headers(denied), json=body)).status_code == 403
    assert (await client.get(route)).status_code == 401
    assert (
        await client.patch(
            route + "/" + object_id,
            headers=command_headers(current),
            json={"expected_version": 1, "status": "ACTIVE"},
        )
    ).status_code == 422
    assert (
        await client.get(route, headers=current, params={"is_active": "true"})
    ).status_code == 422


async def test_product_denies_cover_child_atomicity_lists_and_replay(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, current, body = await setup_product(factory, tenant_a)
    route = f"/v1/companies/{company}/product-families"
    receipt = command_headers(current)
    await policy(factory, tenant_a, company, user, "catalog.item", "sku", "write")
    result = await client.post(route, headers=receipt, json=body)
    assert result.status_code == 403, result.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductFamily.id))) == 0
            assert (
                await db.scalar(select(func.count(Outbox.id)).where(Outbox.tenant_id == tenant_a))
                == 0
            )
    await policy(
        factory, tenant_a, company, user, "catalog.product_family", "description", "read", version=4
    )
    created = await client.post(route, headers=receipt, json={**body, "description": "Private"})
    assert created.status_code == 201, created.text
    assert "description" not in created.json()["family"]
    await policy(factory, tenant_a, company, user, "catalog.item", "sku", "write", version=5)
    assert (
        await client.post(route, headers=receipt, json={**body, "description": "Private"})
    ).status_code == 403
    await policy(
        factory, tenant_a, company, user, "catalog.product_family", "code", "read", version=6
    )
    assert (await client.get(route, headers=current, params={"q": "PRODUCT"})).status_code == 403
    assert (await client.get(route, headers=current, params={"sort": "code"})).status_code == 403
    page = await client.get(route, headers=current)
    assert page.status_code == 200 and "code" not in page.json()["items"][0]


async def test_referenced_unit_cannot_change_product_quantity_semantics(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, current, body = await setup_product(factory, tenant_a)
    route = f"/v1/companies/{company}"
    created = await client.post(
        route + "/product-families", headers=command_headers(current), json=body
    )
    assert created.status_code == 201, created.text
    unit_auth = headers(
        company, tenant=tenant_a, user=user, permission=["unit.read", "unit.manage"]
    )
    unit = route + "/units/" + body["default_item"]["base_unit_id"]
    result = await client.patch(
        unit,
        headers=command_headers(unit_auth),
        json={"expected_version": 1, "decimal_places": 2, "quantity_increment": "0.01"},
    )
    assert result.status_code == 409, result.text
    result = await client.post(
        unit + "/deactivate", headers=command_headers(unit_auth), json={"expected_version": 1}
    )
    assert result.status_code == 409, result.text


async def test_product_write_conditions_see_resulting_version(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, current, body = await setup_product(factory, tenant_a)
    route = f"/v1/companies/{company}/product-families"
    created = await client.post(route, headers=command_headers(current), json=body)
    assert created.status_code == 201, created.text
    await policy(
        factory,
        tenant_a,
        company,
        user,
        "catalog.product_family",
        "name",
        "write",
        condition={"field": "row_version", "cmp": "gte", "value": "2"},
    )
    response = await client.patch(
        route + "/" + created.json()["family"]["id"],
        headers=command_headers(current),
        json={"expected_version": 1, "name": "Denied"},
    )
    assert response.status_code == 403, response.text


async def test_product_keeps_referenced_brand_and_type_available(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from catalog.models import ProductTypeRevision

    company, user, current, body = await setup_product(factory, tenant_a)
    prefix = f"/v1/companies/{company}"
    manage = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            "brand.read",
            "brand.manage",
            "brand_series.read",
            "brand_series.manage",
            "product_type.read",
            "product_type.manage",
        ],
    )
    brand = await client.post(
        prefix + "/brands", headers=command_headers(manage), json={"code": "BRAND", "name": "Brand"}
    )
    assert brand.status_code == 201, brand.text
    series = await client.post(
        prefix + "/brand-series",
        headers=command_headers(manage),
        json={"code": "SERIES", "name": "Series", "brand_id": brand.json()["id"]},
    )
    assert series.status_code == 201, series.text
    body.update(brand_id=brand.json()["id"], series_id=series.json()["id"])
    created = await client.post(
        prefix + "/product-families", headers=command_headers(current), json=body
    )
    assert created.status_code == 201, created.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            revision = await db.get(
                ProductTypeRevision, uuid.UUID(body["product_type_revision_id"])
            )
            assert revision is not None
            type_id = revision.product_type_id
    for route in ("brand-series/" + series.json()["id"], "product-types/" + str(type_id)):
        response = await client.post(
            prefix + "/" + route + "/deactivate",
            headers=command_headers(manage),
            json={"expected_version": 1},
        )
        assert response.status_code == 409, response.text
