from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.tasks.index_rebuilds import build_chunk, permissions
from tests.commercial_factories import auth, reference_data
from tests.source_factories import all_facts
from tests.test_actor_authorization import proof
from tests.test_api import headers
from tests.test_classification_api import create
from tests.test_commercial_api import command_headers
from tests.test_index_rebuilds import filter_query


async def test_commercial_option_sources_obey_parent_and_active_scope(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    await reference_data(factory)
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    base = f"/v1/companies/{company}/option-sources/"
    for path, source, child_path, child_source, parent_field, extra in [
        ("brands", "catalog.brands", "brand-series", "catalog.brand_series", "brand_id", {}),
        (
            "manufacturers",
            "catalog.manufacturers",
            "manufacturer-sites",
            "catalog.manufacturer_sites",
            "manufacturer_id",
            {"country_code": "IN"},
        ),
    ]:
        parent = (
            await create(client, company, current, path, {"code": "P", "name": "Parent"})
        ).json()
        other = (
            await create(client, company, current, path, {"code": "Q", "name": "Other"})
        ).json()
        child = await create(
            client,
            company,
            current,
            child_path,
            {"code": "C", "name": "Child", parent_field: parent["id"], **extra},
        )
        assert child.status_code == 201, child.text
        assert (await client.get(base + source, headers=current)).json()["items"][0][
            "value"
        ] == parent["id"]
        assert (await client.get(base + child_source, headers=current)).status_code == 422
        options = await client.get(
            base + child_source, headers=current, params={"parent_id": parent["id"], "q": "Ch"}
        )
        assert (
            options.status_code == 200 and options.json()["items"][0]["value"] == child.json()["id"]
        )
        assert (
            await client.get(
                base + child_source, headers=current, params={"parent_id": other["id"]}
            )
        ).json()["items"] == []
        master = f"/v1/companies/{company}/{path}/{parent['id']}"
        assert (
            await client.post(
                master + "/deactivate",
                headers=command_headers(current),
                json={"expected_version": 1},
            )
        ).status_code == 409
        child_route = f"/v1/companies/{company}/{child_path}/{child.json()['id']}"
        assert (
            await client.post(
                child_route + "/deactivate",
                headers=command_headers(current),
                json={"expected_version": 1},
            )
        ).status_code == 200
        assert (
            await client.post(
                master + "/deactivate",
                headers=command_headers(current),
                json={"expected_version": 1},
            )
        ).status_code == 200
        assert (
            await client.get(
                base + child_source, headers=current, params={"parent_id": parent["id"]}
            )
        ).status_code == 422
        assert (
            await client.post(
                child_route + "/activate",
                headers=command_headers(current),
                json={"expected_version": 2},
            )
        ).status_code == 409
    product_type = await create(
        client,
        company,
        current,
        "product-types",
        {"code": "SERVICE", "name": "Service", "kind": "SERVICE"},
    )
    assert (await client.get(base + "catalog.product_types", headers=current)).json()["items"][0][
        "value"
    ] == product_type.json()["id"]


@pytest.mark.parametrize(
    ("path", "entity"),
    [("brands", "brand"), ("manufacturers", "manufacturer"), ("product-types", "product_type")],
)
async def test_commercial_custom_index_rebuild_and_dual_write(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    path: str,
    entity: str,
) -> None:
    company, user = uuid7(), uuid7()
    native = "catalog." + entity
    facts = tuple(
        SnapshotRecord(kind=row.kind, id=row.id, data={**row.data, "entity_type": native})
        if row.kind in {"custom_definition", "field_config"}
        else row
        for row in all_facts(company, user)
    )
    current = await auth(factory, tenant_a, company, user, facts=facts)
    body: dict[str, Any] = {
        "code": "A",
        "name": "Alpha",
        "custom_fields": {"cf_note": "alpha"},
        **({"kind": "GOODS"} if entity == "product_type" else {}),
    }
    first = await create(client, company, current, path, body)
    assert first.status_code == 201, first.text
    searchable = tuple(
        row.model_copy(update={"data": {**row.data, "is_searchable": True}})
        if row.kind == "custom_definition"
        else row
        for row in facts
    )
    current = await auth(factory, tenant_a, company, user, facts=searchable, version=3)
    current = headers(company, tenant=tenant_a, user=user, permission=sorted(permissions(native)))
    route = f"/v1/companies/{company}/{path}"
    assert (
        await client.get(route, headers=current, params=filter_query("alpha"))
    ).status_code == 409
    job = await client.post(
        f"/v1/companies/{company}/entities/{native}/field-indexes/cf_note/rebuilds",
        headers=command_headers(current),
        json={"expected_version": 0},
    )
    assert job.status_code == 201, job.text
    second = await create(
        client, company, current, path, {**body, "code": "B", "custom_fields": {"cf_note": "beta"}}
    )
    assert second.status_code == 201, second.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await build_chunk(
                db,
                proof(tenant_a, company, user, source_version=3, permissions=permissions(native)),
                company=company,
                entity=native,
                key="cf_note",
                job_id=uuid.UUID(job.json()["id"]),
                limit=25,
            )
    page = await client.get(route, headers=current, params=filter_query("alpha"))
    assert page.status_code == 200, page.text
    assert [row["id"] for row in page.json()["items"]] == [first.json()["id"]]
    update = await client.patch(
        route + "/" + first.json()["id"],
        headers=command_headers(current),
        json={"expected_version": 1, "custom_fields": {"cf_note": "beta"}},
    )
    assert update.status_code == 200, update.text
    assert (await client.get(route, headers=current, params=filter_query("alpha"))).json()[
        "items"
    ] == []
    assert (
        len((await client.get(route, headers=current, params=filter_query("beta"))).json()["items"])
        == 2
    )


async def test_dynamic_series_selection_revalidates_changed_parent(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    first = (await create(client, company, current, "brands", {"code": "A", "name": "A"})).json()
    second = (await create(client, company, current, "brands", {"code": "B", "name": "B"})).json()
    series = (
        await create(
            client,
            company,
            current,
            "brand-series",
            {"code": "S", "name": "S", "brand_id": first["id"]},
        )
    ).json()
    original = all_facts(company, user)
    template = next(row for row in original if row.kind == "custom_definition")
    parent = SnapshotRecord(
        kind="custom_definition",
        id=uuid7(),
        data={
            **template.data,
            "entity_type": "catalog.product_type",
            "key": "cf_brand",
            "label": "Brand",
            "data_type": "dynamic_select",
            "option_source_key": "catalog.brands",
        },
    )
    facts = tuple(
        SnapshotRecord(
            kind=row.kind,
            id=row.id,
            data={
                **row.data,
                "entity_type": "catalog.product_type",
                **(
                    {
                        "data_type": "dynamic_select",
                        "option_source_key": "catalog.brand_series",
                        "depends_on_key": "cf_brand",
                    }
                    if row.kind == "custom_definition"
                    else {}
                ),
            },
        )
        if row.kind in {"custom_definition", "field_config"}
        else row
        for row in original
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, parent))
    body = {
        "code": "T",
        "name": "Type",
        "kind": "GOODS",
        "custom_fields": {"cf_brand": first["id"], "cf_note": series["id"]},
    }
    created = await create(client, company, current, "product-types", body)
    assert created.status_code == 201, created.text
    updated = await client.patch(
        f"/v1/companies/{company}/product-types/{created.json()['id']}",
        headers=command_headers(current),
        json={"expected_version": 1, "custom_fields": {"cf_brand": second["id"]}},
    )
    assert updated.status_code == 422, updated.text
