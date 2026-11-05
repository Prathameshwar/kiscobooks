"""Product custom-field regression coverage."""

import json
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ProductFamily
from catalog.models.custom_fields import CustomFieldSequence
from catalog.tasks.index_rebuilds import build_chunk, permissions
from tests.product_factories import setup_product
from tests.test_actor_authorization import proof
from tests.test_api import headers
from tests.test_bulk_products_prices import reviewed_commit
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers
from tests.test_product_custom_fields import custom_facts, install

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_product_custom_values_merge_clear_and_replay(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    await install(
        factory,
        tenant_a,
        company,
        user,
        [
            {"key": "cf_note", "entity_type": "catalog.product_family"},
            {"key": "cf_note"},
            {"key": "cf_more"},
        ],
    )
    body["custom_fields"] = {"cf_note": "family"}
    body["default_item"]["custom_fields"] = {"cf_note": "sku", "cf_more": "retained"}
    root = f"/v1/companies/{company}"
    response = await client.post(
        root + "/product-families", headers=command_headers(auth), json=body
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["family"]["custom_fields"] == {"cf_note": "family"}
    assert data["default_item"]["custom_fields"]["cf_note"] == "sku"
    path = root + "/items/" + data["default_item"]["id"]
    request = command_headers(auth)
    payload = {"expected_version": 1, "custom_fields": {"cf_note": None}}
    changed = await client.patch(path, headers=request, json=payload)
    assert changed.status_code == 200, changed.text
    assert changed.json()["custom_fields"] == {"cf_note": None, "cf_more": "retained"}
    replay = await client.patch(path, headers=request, json=payload)
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["row_version"] == 2


async def test_product_custom_read_denies_cover_detail_metadata_and_replay(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    facts = custom_facts(company, user, [{}])
    await setup_source(factory, tenant_a, company, user, facts=facts, version=3)
    root = f"/v1/companies/{company}"
    body["default_item"]["custom_fields"] = {"cf_note": "secret"}
    request = command_headers(auth)
    created = await client.post(root + "/product-families", headers=request, json=body)
    assert created.status_code == 201, created.text
    template = next(row for row in facts if row.kind == "field_policy")
    denied = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **template.data,
            "entity_type": "catalog.item",
            "field_key": "custom_field:cf_note",
            "subject_type": "user",
            "subject_id": str(user),
            "access": "read",
        },
    )
    await setup_source(factory, tenant_a, company, user, facts=(*facts, denied), version=4)
    detail = await client.get(root + "/items/" + created.json()["default_item"]["id"], headers=auth)
    assert detail.status_code == 200 and detail.json()["custom_fields"] == {}
    metadata = await client.get(root + "/entities/catalog.item/field-set", headers=auth)
    assert metadata.status_code == 200
    assert "cf_note" not in {row["key"] for row in metadata.json()["fields"]}
    replay = await client.post(root + "/product-families", headers=request, json=body)
    assert replay.status_code == 201 and replay.json()["default_item"]["custom_fields"] == {}


async def test_retired_field_value_is_preserved_but_cannot_change(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    body["default_item"]["custom_fields"] = {"cf_note": "old"}
    root = f"/v1/companies/{company}"
    created = await client.post(
        root + "/product-families", headers=command_headers(auth), json=body
    )
    assert created.status_code == 201, created.text
    await install(factory, tenant_a, company, user, [{"is_active": False}])
    path = root + "/items/" + created.json()["default_item"]["id"]
    changed = await client.patch(
        path, headers=command_headers(auth), json={"expected_version": 1, "name": "Renamed"}
    )
    assert changed.status_code == 200 and changed.json()["custom_fields"] == {"cf_note": "old"}
    denied = await client.patch(
        path,
        headers=command_headers(auth),
        json={
            "expected_version": 2,
            "custom_fields": {"cf_note": "new"},
        },
    )
    assert denied.status_code == 422


async def test_product_searchable_scalar_backfill_and_query(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    body["default_item"]["custom_fields"] = {"cf_note": "needle"}
    root = f"/v1/companies/{company}"
    created = await client.post(
        root + "/product-families", headers=command_headers(auth), json=body
    )
    assert created.status_code == 201, created.text
    await install(factory, tenant_a, company, user, [{"is_searchable": True}])
    auth = headers(
        company, tenant=tenant_a, user=user, permission=sorted(permissions("catalog.item"))
    )
    started = await client.post(
        root + "/entities/catalog.item/field-indexes/cf_note/rebuilds",
        headers=command_headers(auth),
        json={"expected_version": 0},
    )
    assert started.status_code == 201, started.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            result = await build_chunk(
                db,
                proof(
                    tenant_a,
                    company,
                    user,
                    source_version=3,
                    permissions=permissions("catalog.item"),
                ),
                company=company,
                entity="catalog.item",
                key="cf_note",
                job_id=uuid.UUID(started.json()["id"]),
            )
            assert result.status == "succeeded"
    filtered = await client.get(
        root + "/items",
        headers=auth,
        params={
            "custom_filters": json.dumps(
                [
                    {"key": "cf_note", "operator": "eq", "value": "needle"},
                ]
            )
        },
    )
    assert filtered.status_code == 200, filtered.text
    assert [row["id"] for row in filtered.json()["items"]] == [created.json()["default_item"]["id"]]


async def test_autonumber_create_replay_allocates_once(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, body = await setup_product(factory, tenant_a)
    await install(
        factory,
        tenant_a,
        company,
        user,
        [
            {
                "data_type": "auto_number",
                "sequence_config": {"prefix": "IT-", "padding": 3, "start": 1, "reset": "never"},
            }
        ],
    )
    root = f"/v1/companies/{company}/product-families"
    request = command_headers(auth)
    first = await client.post(root, headers=request, json=body)
    assert first.status_code == 201, first.text
    second = await client.post(root, headers=request, json=body)
    assert second.status_code == 201 and second.headers["Idempotency-Replayed"] == "true"
    assert first.json()["default_item"]["custom_fields"]["cf_note"] == "IT-001"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (await db.scalars(select(CustomFieldSequence.next_value))).one() == 2


async def test_bulk_product_create_and_custom_value_update_use_native_handlers(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, _, body = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    body["default_item"]["custom_fields"] = {"cf_note": "initial"}
    await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        user,
        auth,
        {
            "format": "JSON",
            "records": [
                {
                    "key": "family",
                    "change_set": "product",
                    "resource": "product_family",
                    "data": body,
                },
                {
                    "key": "sku",
                    "change_set": "product",
                    "resource": "item",
                    "action": "UPDATE",
                    "target": {"record": "family", "field": "default_item.id"},
                    "data": {"custom_fields": {"cf_note": "bulk changed"}},
                },
            ],
        },
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (await db.scalars(select(Item.custom_fields))).one() == {
                "cf_note": "bulk changed"
            }
            assert len(list(await db.scalars(select(ProductFamily)))) == 1
