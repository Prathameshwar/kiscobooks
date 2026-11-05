"""Native identifier master workflows and controls used by the console UI."""

import json
import uuid
from pathlib import Path

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import IdempotencyKey, ItemBarcode, Outbox
from tests.product_definition_factories import seed_definitions
from tests.test_api import headers
from tests.test_unit_api import policy, seed_context

RESOURCES = [
    (
        "identifier-types",
        "identifier_type",
        {"code": "MPN", "name": "Part number", "is_barcode": False},
    ),
    (
        "identifier-namespaces",
        "identifier_namespace",
        {"code": "OEM", "name": "Manufacturer namespace"},
    ),
]


def current(tenant, company, user, permission, key=None):
    return {
        **headers(company, tenant=tenant, user=user, permission=permission),
        **({"Idempotency-Key": key} if key else {}),
    }


@pytest.mark.parametrize("resource,permission,body", RESOURCES)
async def test_referenced_identifier_cannot_retire(
    client, factory, tenant_a, resource, permission, body
):
    company, ids = await seed_definitions(factory, tenant_a)
    user = ids["actor_user"]
    await seed_context(factory, tenant_a, company, user, version=3)
    base = f"/v1/companies/{company}/{resource}"
    created = await client.post(
        base, json=body, headers=current(tenant_a, company, user, permission + ".manage", "create")
    )
    assert created.status_code == 201, created.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            barcode = await db.get(ItemBarcode, ids["item_barcode"])
            assert barcode is not None
            if resource == "identifier-types":
                barcode.identifier_type_code = body["code"]
            else:
                barcode.namespace_code = body["code"]
        async with factory() as db:
            before = len((await db.scalars(select(Outbox))).all())
    retired = await client.post(
        base + "/" + created.json()["id"] + "/deactivate",
        json={"expected_version": 1},
        headers=current(tenant_a, company, user, permission + ".manage", "retire"),
    )
    assert retired.status_code == 409, retired.text
    detail = await client.get(
        base + "/" + created.json()["id"],
        headers=current(tenant_a, company, user, permission + ".read"),
    )
    assert detail.json()["row_version"] == 1
    assert detail.json()["is_active"] is True
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert len((await db.scalars(select(Outbox))).all()) == before


@pytest.mark.parametrize("resource,permission,body", RESOURCES)
async def test_native_workflow_and_atomic_audit(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    resource: str,
    permission: str,
    body: dict,
) -> None:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    base = f"/v1/companies/{company}/{resource}"
    writer = current(tenant_a, company, user, permission + ".manage", "create")
    reader = current(tenant_a, company, user, permission + ".read")
    assert (await client.post(base, json=body)).status_code == 401
    assert (
        await client.post(base, json=body, headers={**reader, "Idempotency-Key": "deny"})
    ).status_code == 403
    created = await client.post(base, json=body, headers=writer)
    assert created.status_code == 201, created.text
    detail = created.headers["Location"]
    assert created.json()["row_version"] == 1 and created.json()["is_active"] is True
    replay = await client.post(base, json=body, headers=writer)
    assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    assert (await client.get(detail, headers=reader)).json() == created.json()
    assert (
        await client.post(base, json=body, headers={**writer, "Idempotency-Key": "duplicate"})
    ).status_code == 409
    changed = await client.patch(
        detail,
        json={"expected_version": 1, "name": "Reviewed name"},
        headers={**writer, "Idempotency-Key": "edit"},
    )
    assert changed.status_code == 200 and changed.json()["row_version"] == 2, changed.text
    assert (
        await client.patch(
            detail,
            json={"expected_version": 1, "name": "Stale"},
            headers={**writer, "Idempotency-Key": "stale"},
        )
    ).status_code == 409
    for extra in ({"code": "CHANGED"}, {"is_active": False}, {"is_barcode": True}):
        assert (
            await client.patch(
                detail,
                json={"expected_version": 2, **extra},
                headers={**writer, "Idempotency-Key": uuid.uuid4().hex},
            )
        ).status_code == 422
    retired = await client.post(
        detail + "/deactivate",
        json={"expected_version": 2},
        headers={**writer, "Idempotency-Key": "retire"},
    )
    assert retired.status_code == 200 and retired.json()["is_active"] is False, retired.text
    active = await client.post(
        detail + "/activate",
        json={"expected_version": 3},
        headers={**writer, "Idempotency-Key": "activate"},
    )
    assert active.status_code == 200 and active.json()["row_version"] == 4
    replay_retirement = await client.post(
        detail + "/deactivate",
        json={"expected_version": 2},
        headers={**writer, "Idempotency-Key": "retire"},
    )
    assert replay_retirement.status_code == 200
    assert replay_retirement.headers["Idempotency-Replayed"] == "true"
    assert replay_retirement.json()["is_active"] is True
    assert replay_retirement.json()["row_version"] == 4
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert len(list(await db.scalars(select(Outbox)))) == 4
            assert len(list(await db.scalars(select(IdempotencyKey)))) == 4


@pytest.mark.parametrize("resource,permission,body", RESOURCES)
async def test_company_and_tenant_boundaries(
    client,
    factory,
    tenant_a,
    tenant_b,
    resource,
    permission,
    body,
):
    company, other, foreign, user = uuid7(), uuid7(), uuid7(), uuid7()
    for tenant, target in [(tenant_a, company), (tenant_a, other), (tenant_b, foreign)]:
        await seed_context(factory, tenant, target, user)
    base = f"/v1/companies/{company}/{resource}"
    created = await client.post(
        base, json=body, headers=current(tenant_a, company, user, permission + ".manage", "create")
    )
    assert created.status_code == 201, created.text
    object_id = created.json()["id"]
    for tenant, target in [(tenant_a, other), (tenant_b, foreign)]:
        expected = 403 if tenant == tenant_a else 404
        route = f"/v1/companies/{target}/{resource}"
        reader = current(tenant, target, user, permission + ".read")
        assert (await client.get(route, headers=reader)).json()["items"] == []
        assert (await client.get(route + "/" + object_id, headers=reader)).status_code == expected
        assert (
            await client.patch(
                route + "/" + object_id,
                json={"expected_version": 1, "name": "Foreign"},
                headers=current(tenant, target, user, permission + ".manage", "foreign"),
            )
        ).status_code == expected
    wrong = current(tenant_a, other, user, permission + ".read")
    assert (await client.get(base, headers=wrong)).status_code == 403


@pytest.mark.parametrize("resource,permission,body", RESOURCES)
async def test_protected_reads_writes_replay_and_queries(
    client, factory, tenant_a, resource, permission, body
):
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    entity, base = "catalog." + permission, f"/v1/companies/{company}/{resource}"
    writer = current(tenant_a, company, user, permission + ".manage", "create")
    reader = current(tenant_a, company, user, permission + ".read")
    created = await client.post(base, json=body, headers=writer)
    assert created.status_code == 201, created.text
    detail = created.headers["Location"]
    await seed_context(
        factory, tenant_a, company, user, (policy(user, "code", "read", entity=entity),), version=3
    )
    assert "code" not in (await client.get(detail, headers=reader)).json()
    assert "code" not in (await client.get(base, headers=reader)).json()["items"][0]
    assert (await client.get(base, params={"q": body["code"]}, headers=reader)).status_code == 403
    assert (await client.get(base, params={"sort": "code"}, headers=reader)).status_code == 403
    await seed_context(
        factory, tenant_a, company, user, (policy(user, "name", "write", entity=entity),), version=4
    )
    assert (await client.post(base, json=body, headers=writer)).status_code == 403
    assert (
        await client.patch(
            detail,
            json={"expected_version": 1, "name": "Denied"},
            headers={**writer, "Idempotency-Key": "denied"},
        )
    ).status_code == 403


@pytest.mark.parametrize("resource,permission,body", RESOURCES)
async def test_closed_indexed_lists_and_inputs(
    client, factory, tenant_a, resource, permission, body
):
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    base = f"/v1/companies/{company}/{resource}"
    writer = current(tenant_a, company, user, permission + ".manage", "create")
    reader = current(tenant_a, company, user, permission + ".read")
    for index in range(3):
        result = await client.post(
            base,
            json={**body, "code": "ID" + str(index)},
            headers={**writer, "Idempotency-Key": str(index)},
        )
        assert result.status_code == 201, result.text
    first = await client.get(base, headers=reader, params={"q": "ID", "limit": 1, "sort": "code"})
    assert first.status_code == 200 and first.json()["page"]["has_more"]
    cursor = first.json()["page"]["next_cursor"]
    following = await client.get(
        base, headers=reader, params={"q": "ID", "limit": 1, "sort": "code", "cursor": cursor}
    )
    assert following.json()["items"][0]["id"] != first.json()["items"][0]["id"]
    for query in (
        {"sort": "name"},
        {"unknown": "true"},
        {"cursor": "bad"},
        {"q": "ID", "limit": 2, "sort": "code", "cursor": cursor},
    ):
        assert (await client.get(base, headers=reader, params=query)).status_code == 422
    assert (await client.get(base + "?limit=1&limit=2", headers=reader)).status_code == 422
    for invalid in ({"code": "lower"}, {"name": "\n"}, {"name": ""}, {"extra": True}):
        assert (
            await client.post(base, json={**body, **invalid}, headers=writer)
        ).status_code == 422


async def test_native_controls_and_operation_metadata(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    permissions = [
        "unit.read",
        "unit.manage",
        "pack_type.read",
        "pack_type.manage",
        "identifier_type.read",
        "identifier_type.manage",
        "identifier_namespace.read",
        "identifier_namespace.manage",
        "identifier_profile.read",
        "identifier_profile.manage",
    ]
    auth = current(tenant_a, company, user, permissions)
    entities = [
        "unit_conversion",
        "pack_type",
        "identifier_type",
        "identifier_namespace",
        "identifier_profile",
        "identifier_profile_requirement",
    ]
    captured = {}
    for entity in entities:
        base = f"/v1/companies/{company}/entities/catalog.{entity}/field-set"
        for operation in ("create", "update"):
            response = await client.get(base, headers=auth, params={"operation": operation})
            assert response.status_code == 200, response.text
            captured[entity + ":" + operation] = response.json()
        fields = {row["key"]: row for row in captured[entity + ":create"]["fields"]}
        if entity == "unit_conversion":
            assert fields["numerator"]["control"]["kind"] == "text"
            assert fields["from_unit_id"]["control"]["reference_source"] == "units"
            assert not any(row["writable"] for row in captured[entity + ":update"]["fields"])
        if entity.startswith("identifier_") and entity in {
            "identifier_type",
            "identifier_namespace",
        }:
            assert not next(
                row for row in captured[entity + ":update"]["fields"] if row["key"] == "code"
            )["writable"]
    destination = (
        Path(__file__).resolve().parents[3] / ".tools/units-identifiers-review/native-fields.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(captured, indent=2), encoding="utf-8")
