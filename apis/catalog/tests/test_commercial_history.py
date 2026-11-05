from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Outbox
from tests.commercial_factories import auth
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import create
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_production_interval_workflow(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    brand = (
        await create(client, company, current, "brands", {"code": "B", "name": "Brand"})
    ).json()
    maker = (
        await create(client, company, current, "manufacturers", {"code": "M", "name": "Maker"})
    ).json()
    body = {
        "brand_id": brand["id"],
        "manufacturer_id": maker["id"],
        "production_role": "OEM",
        "valid_from": "2020-01-01",
    }
    route = f"/v1/companies/{company}/brand-manufacturers"
    assert (await client.post(route, json=body)).status_code == 401
    denied = headers(company, tenant=tenant_a, user=user, permission="brand_manufacturer.read")
    assert (await client.post(route, headers=command_headers(denied), json=body)).status_code == 403
    receipt = command_headers(current)
    result = await client.post(route, headers=receipt, json=body)
    assert result.status_code == 201, result.text
    first = result.json()
    replay = await client.post(route, headers=receipt, json=body)
    assert replay.status_code == 201 and replay.json() == first
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert (
        await client.post(route, headers=receipt, json={**body, "production_role": "ASSEMBLER"})
    ).status_code == 422
    assert (await create(client, company, current, "brand-manufacturers", body)).status_code == 409
    alternate = await create(
        client,
        company,
        current,
        "brand-manufacturers",
        {**body, "production_role": "ASSEMBLER", "valid_to": "2020-12-31"},
    )
    assert alternate.status_code == 201, alternate.text
    assert (
        await create(
            client, company, current, "brand-manufacturers", {**body, "valid_to": "2019-01-01"}
        )
    ).status_code == 422
    listed = await client.get(
        route,
        headers=current,
        params={"brand_id": brand["id"], "valid_at": "2021-01-01", "limit": 1},
    )
    assert listed.status_code == 200 and listed.json()["items"][0]["id"] == first["id"]
    for query in ({"q": "text"}, {"sort": "name"}, {"extra": "x"}):
        assert (await client.get(route, headers=current, params=query)).status_code == 422
    page = await client.get(route, headers=current, params={"limit": 1, "sort": "-valid_from"})
    assert page.json()["page"]["next_cursor"]
    second = await client.get(
        route,
        headers=current,
        params={"limit": 1, "sort": "-valid_from", "cursor": page.json()["page"]["next_cursor"]},
    )
    assert (
        second.status_code == 200
        and second.json()["items"][0]["id"] != page.json()["items"][0]["id"]
    )
    detail = route + "/" + first["id"]
    assert (await client.get(detail, headers=current)).json()["production_role"] == "OEM"
    other_company = uuid7()
    other = await auth(factory, tenant_a, other_company, user)
    assert (
        await client.get(detail.replace(str(company), str(other_company)), headers=other)
    ).status_code == 403
    alien = await auth(factory, tenant_b, company, user)
    assert (await client.get(detail, headers=alien)).status_code == 404
    for path, obj in [("brands", brand), ("manufacturers", maker)]:
        target = f"/v1/companies/{company}/{path}/{obj['id']}"
        assert (
            await client.post(
                target + "/deactivate",
                headers=command_headers(current),
                json={"expected_version": 1},
            )
        ).status_code == 409
        assert (
            await client.patch(
                target,
                headers=command_headers(current),
                json={"expected_version": 1, "code": "NEW"},
            )
        ).status_code == 409
    assert (
        await client.post(
            detail + "/close",
            headers=command_headers(current),
            json={"expected_version": 2, "valid_to": "2020-12-31"},
        )
    ).status_code == 409
    assert (
        await client.post(
            detail + "/close",
            headers=command_headers(current),
            json={"expected_version": 1, "valid_to": "2019-01-01"},
        )
    ).status_code == 409
    close_receipt = command_headers(current)
    closed = await client.post(
        detail + "/close",
        headers=close_receipt,
        json={"expected_version": 1, "valid_to": "2020-12-31"},
    )
    assert closed.status_code == 200 and closed.json()["row_version"] == 2
    assert (
        await client.post(
            detail + "/close",
            headers=close_receipt,
            json={"expected_version": 1, "valid_to": "2020-12-31"},
        )
    ).headers["Idempotency-Replayed"] == "true"
    assert (
        await client.post(
            detail + "/close",
            headers=command_headers(current),
            json={"expected_version": 2, "valid_to": "2021-12-31"},
        )
    ).status_code == 409
    noop = await client.post(
        detail + "/close",
        headers=command_headers(current),
        json={"expected_version": 2, "valid_to": "2020-12-31"},
    )
    assert noop.json()["row_version"] == 2
    for path, obj in [("brands", brand), ("manufacturers", maker)]:
        target = f"/v1/companies/{company}/{path}/{obj['id']}"
        assert (
            await client.post(
                target + "/deactivate",
                headers=command_headers(current),
                json={"expected_version": 1},
            )
        ).status_code == 200
    assert (
        await create(
            client, company, current, "brand-manufacturers", {**body, "valid_from": "2021-01-01"}
        )
    ).status_code == 409
    with tenant_scope(tenant_a):
        async with factory() as db:
            events = list(
                await db.scalars(
                    select(Outbox).where(Outbox.event_type.like("catalog.brand_manufacturer.%"))
                )
            )
            assert len(events) == 3
            assert all(event.payload["company_id"] == str(company) for event in events)


@pytest.mark.parametrize("kind", ["GOODS", "SERVICE"])
async def test_type_revision_publication_workflow(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    kind: str,
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    product_type = (
        await create(
            client,
            company,
            current,
            "product-types",
            {"code": "TYPE", "name": "Type", "kind": kind},
        )
    ).json()
    route = f"/v1/companies/{company}/product-types/{product_type['id']}/revisions"
    body = {
        "inventory_modes": ["STOCK" if kind == "GOODS" else "NON_STOCK"],
        "tracking_modes": ["NONE"],
        "unit_dimensions": ["COUNT" if kind == "GOODS" else "TIME"],
    }
    assert (await client.post(route, json=body)).status_code == 401
    reader = headers(company, tenant=tenant_a, user=user, permission="product_type.read")
    assert (await client.post(route, headers=command_headers(reader), json=body)).status_code == 403
    receipt = command_headers(current)
    created = await client.post(route, headers=receipt, json=body)
    assert created.status_code == 201, created.text
    first = created.json()
    assert first["revision"] == 1 and first["kind"] == kind and first["published_at"] is None
    assert (await client.post(route, headers=receipt, json=body)).json() == first
    assert (
        await client.post(
            route, headers=command_headers(current), json={**body, "inventory_modes": []}
        )
    ).status_code == 422
    detail = route + "/" + first["id"]
    assert (await client.get(detail, headers=current)).status_code == 200
    wrong_type = (
        await create(
            client,
            company,
            current,
            "product-types",
            {"code": "OTHER", "name": "Other", "kind": kind},
        )
    ).json()
    assert (
        await client.get(detail.replace(product_type["id"], wrong_type["id"]), headers=current)
    ).status_code == 403
    other_company = uuid7()
    other = await auth(factory, tenant_a, other_company, user)
    assert (
        await client.get(detail.replace(str(company), str(other_company)), headers=other)
    ).status_code == 403
    alien = await auth(factory, tenant_b, company, user)
    assert (await client.get(detail, headers=alien)).status_code == 404
    assert (
        await client.patch(
            detail,
            headers=command_headers(current),
            json={"expected_version": 2, "allow_variants": False},
        )
    ).status_code == 409
    assert (
        await client.patch(
            detail,
            headers=command_headers(current),
            json={"expected_version": 1, "allow_variants": None},
        )
    ).status_code == 422
    updated = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 1, "allow_variants": False},
    )
    assert updated.status_code == 200 and updated.json()["row_version"] == 2
    noop = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 2, "allow_variants": False},
    )
    assert noop.status_code == 200 and noop.json()["row_version"] == 2
    editor = headers(
        company, tenant=tenant_a, user=user, permission=["product_type.read", "product_type.manage"]
    )
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(editor), json={"expected_version": 2}
        )
    ).status_code == 403
    publish_receipt = command_headers(current)
    published = await client.post(
        detail + "/publish", headers=publish_receipt, json={"expected_version": 2}
    )
    assert (
        published.status_code == 200
        and published.json()["published_at"]
        and published.json()["row_version"] == 3
    )
    assert (
        await client.post(
            detail + "/publish", headers=publish_receipt, json={"expected_version": 2}
        )
    ).headers["Idempotency-Replayed"] == "true"
    assert (
        await client.patch(
            detail,
            headers=command_headers(current),
            json={"expected_version": 3, "allow_variants": True},
        )
    ).status_code == 409
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 3}
        )
    ).status_code == 409
    second = await client.post(route, headers=command_headers(current), json=body)
    assert second.json()["revision"] == 2
    for published_value, expected in ((True, first["id"]), (False, second.json()["id"])):
        listed = await client.get(route, headers=current, params={"published": published_value})
        assert listed.status_code == 200 and listed.json()["items"][0]["id"] == expected
        assert "inventory_modes" not in listed.json()["items"][0]
    first_page = await client.get(route, headers=current, params={"limit": 1, "sort": "-revision"})
    assert first_page.status_code == 200, first_page.text
    next_page = await client.get(
        route,
        headers=current,
        params={
            "limit": 1,
            "sort": "-revision",
            "cursor": first_page.json()["page"]["next_cursor"],
        },
    )
    assert next_page.status_code == 200 and next_page.json()["items"][0]["revision"] == 1
    for query in ({"q": "text"}, {"sort": "code"}):
        assert (await client.get(route, headers=current, params=query)).status_code == 422
    master = route.rsplit("/", 1)[0]
    for change in ({"code": "CHANGED"}, {"kind": "BOTH"}):
        assert (
            await client.patch(
                master, headers=command_headers(current), json={"expected_version": 1, **change}
            )
        ).status_code == 409
    assert (
        await client.post(
            master + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    assert (
        await client.post(route, headers=command_headers(current), json=body)
    ).status_code == 409
    assert (
        await client.patch(
            route + "/" + second.json()["id"],
            headers=command_headers(current),
            json={"expected_version": 1, "require_brand": True},
        )
    ).status_code == 409
    metadata = await client.get(
        f"/v1/companies/{company}/entities/catalog.product_type_revision/field-set", headers=current
    )
    assert metadata.status_code == 200, metadata.text
    fields = {field["key"]: field for field in metadata.json()["fields"]}
    assert all(
        not fields[key]["writable"]
        for key in ("revision", "row_version", "kind", "product_type_id", "published_at")
    )


async def test_history_field_denies_block_filters_publish_and_replay(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    current = await auth(factory, tenant_a, company, user, facts=facts)
    product_type = (
        await create(
            client,
            company,
            current,
            "product-types",
            {"code": "T", "name": "Type", "kind": "GOODS"},
        )
    ).json()
    route = f"/v1/companies/{company}/product-types/{product_type['id']}/revisions"
    body = {
        "inventory_modes": ["STOCK"],
        "tracking_modes": ["BATCH"],
        "unit_dimensions": ["COUNT"],
        "require_expiry": True,
    }
    receipt = command_headers(current)
    first = await client.post(route, headers=receipt, json=body)
    assert first.status_code == 201
    policy = next(row for row in facts if row.kind == "field_policy")
    policies = tuple(
        SnapshotRecord(
            kind="field_policy",
            id=uuid7(),
            data={
                **policy.data,
                "entity_type": entity,
                "subject_type": "user",
                "subject_id": str(user),
                "field_key": field,
                "access": access,
            },
        )
        for entity, field, access in [
            ("catalog.product_type_revision", "require_expiry", "write"),
            ("catalog.product_type_revision", "published_at", "read"),
            ("catalog.brand_manufacturer", "valid_to", "read"),
        ]
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, *policies))
    assert (await client.post(route, headers=receipt, json=body)).status_code == 403
    assert (
        await client.post(
            route + "/" + first.json()["id"] + "/publish",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 403
    assert (await client.get(route, headers=current, params={"published": True})).status_code == 403
    assert (
        await client.get(
            f"/v1/companies/{company}/brand-manufacturers",
            headers=current,
            params={"valid_at": "2026-01-01"},
        )
    ).status_code == 403


async def test_hidden_type_membership_cannot_be_probed_through_nested_revision_routes(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    current = await auth(factory, tenant_a, company, user, facts=facts)
    product_type = (
        await create(
            client,
            company,
            current,
            "product-types",
            {"code": "T", "name": "Type", "kind": "GOODS"},
        )
    ).json()
    route = f"/v1/companies/{company}/product-types/{product_type['id']}/revisions"
    body = {"inventory_modes": ["STOCK"], "tracking_modes": ["NONE"], "unit_dimensions": ["COUNT"]}
    receipt = command_headers(current)
    first = await client.post(route, headers=receipt, json=body)
    assert first.status_code == 201
    policy = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.product_type_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "product_type_id",
            "access": "read",
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, deny))
    assert (await client.get(route + "/" + first.json()["id"], headers=current)).status_code == 403
    assert (await client.get(route, headers=current)).status_code == 403
    assert (await client.post(route, headers=receipt, json=body)).status_code == 403
    assert (
        await client.post(route, headers=command_headers(current), json=body)
    ).status_code == 403
