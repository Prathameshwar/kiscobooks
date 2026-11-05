import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ProductFamily
from tests.product_factories import setup_product
from tests.test_commercial_api import command_headers


async def test_product_tables_are_tenant_isolated_and_default_sku_is_unique(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    records = []
    for tenant in (tenant_a, tenant_b):
        company, _, auth, body = await setup_product(factory, tenant)
        result = await client.post(
            f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
        )
        assert result.status_code == 201, result.text
        records.append((tenant, company, result.json()))
    for tenant, company, _data in records:
        with tenant_scope(tenant):
            async with factory() as db:
                for model in (ProductFamily, Item):
                    rows = list(await db.scalars(select(model)))
                    assert (
                        len(rows) == 1
                        and isinstance(rows[0], ProductFamily | Item)
                        and rows[0].tenant_id == tenant
                        and rows[0].company_id == company
                    )
    tenant, company, data = records[0]
    original = data["default_item"]
    common = {
        "tenant_id": tenant,
        "company_id": company,
        "family_id": uuid.UUID(original["family_id"]),
        "default_slot": 1,
        "sku": "DUPLICATE",
        "name": "Duplicate",
        "base_unit_id": uuid.UUID(original["base_unit_id"]),
        "sellable": True,
        "purchasable": True,
    }
    for override in (
        {},
        {"family_id": uuid.UUID(records[1][2]["family"]["id"]), "default_slot": None},
        {"default_slot": 2},
        {"min_sale_quantity": 0, "default_slot": None},
        {"status": "UNKNOWN", "default_slot": None},
    ):
        with tenant_scope(tenant), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(Item(id=uuid7(), **{**common, **override}))
                await db.flush()


async def test_product_custom_fields_remain_descriptive_and_protected(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from tests.test_master_reference_policy import policy

    company, user, auth, body = await setup_product(factory, tenant_a)
    body["default_item"]["custom_fields"] = {"cf_note": "Internal note"}
    result = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert result.status_code == 201, result.text
    item = result.json()["default_item"]
    assert item["custom_fields"] == {"cf_note": "Internal note"}
    path = f"/v1/companies/{company}/items/" + item["id"]
    changed = await client.patch(
        path,
        headers=command_headers(auth),
        json={"expected_version": 1, "custom_fields": {"cf_note": "Updated note"}},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["custom_fields"]["cf_note"] == "Updated note"
    await policy(factory, tenant_a, company, user, "catalog.item", "custom_field:cf_note", "read")
    hidden = await client.get(path, headers=auth)
    assert hidden.status_code == 200 and hidden.json()["custom_fields"] == {}


async def test_product_custom_index_rebuild_and_filter(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from catalog.tasks.index_rebuilds import build_chunk, permissions
    from tests.source_factories import all_facts
    from tests.test_actor_authorization import proof
    from tests.test_api import headers
    from tests.test_classification_api import setup_source
    from tests.test_index_rebuilds import filter_query

    company, user, auth, body = await setup_product(factory, tenant_a)
    body["default_item"]["custom_fields"] = {"cf_note": "Searchable"}
    created = await client.post(
        f"/v1/companies/{company}/product-families", headers=command_headers(auth), json=body
    )
    assert created.status_code == 201, created.text
    facts = tuple(
        row.model_copy(update={"data": {**row.data, "is_searchable": True}})
        if row.kind == "custom_definition"
        else row
        for row in all_facts(company, user)
    )
    await setup_source(factory, tenant_a, company, user, version=3, facts=facts)
    auth = headers(
        company, tenant=tenant_a, user=user, permission=sorted(permissions("catalog.item"))
    )
    path = f"/v1/companies/{company}/entities/catalog.item/field-indexes/cf_note"
    job = await client.post(
        path + "/rebuilds", headers=command_headers(auth), json={"expected_version": 0}
    )
    assert job.status_code == 201, job.text
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
                job_id=uuid.UUID(job.json()["id"]),
                limit=25,
            )
            assert result.status == "succeeded"
    found = await client.get(
        f"/v1/companies/{company}/items", headers=auth, params=filter_query("Searchable")
    )
    assert found.status_code == 200, found.text
    assert [row["id"] for row in found.json()["items"]] == [created.json()["default_item"]["id"]]
