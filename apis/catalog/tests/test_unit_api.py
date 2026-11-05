from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, cast

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import IdempotencyKey, Outbox, UnitConversion
from catalog.models.projections import ProjectionCheckpoint
from catalog.tasks.projections import activate_snapshot
from tests.source_factories import company_record, snapshot
from tests.test_api import headers

UNIT_BODY: dict[str, Any] = {
    "code": "EA",
    "symbol": "ea",
    "name": "Each",
    "dimension": "COUNT",
    "decimal_places": 0,
    "quantity_increment": "1",
}


async def seed_context(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    policies: tuple[SnapshotRecord, ...] = (),
    *,
    version: int = 2,
) -> None:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(
                db,
                snapshot(
                    tenant,
                    company,
                    (
                        company_record(company),
                        SnapshotRecord(kind="user", id=user, data={"status": "active"}),
                        *policies,
                    ),
                    version=version,
                ),
            )


def access(
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    permission: str,
    *,
    key: str | None = None,
) -> dict[str, str]:
    return {
        **headers(company, tenant=tenant, user=user, permission=permission),
        **({"Idempotency-Key": key} if key else {}),
    }


def policy(
    user: uuid.UUID,
    field: str,
    permission: str,
    *,
    entity: str = "catalog.unit_of_measure",
    condition: dict[str, Any] | None = None,
) -> SnapshotRecord:
    return SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            "subject_type": "user",
            "subject_id": str(user),
            "entity_type": entity,
            "field_key": field,
            "access": permission,
            "effect": "deny",
            "scope_type": "tenant",
            "scope_id": str(uuid.UUID(int=0)),
            "condition": condition,
            "is_active": True,
        },
    )


@pytest.mark.parametrize("pack", [False, True])
async def test_complete_master_workflow(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    pack: bool,
) -> None:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    resource, permission = ("pack-types", "pack_type") if pack else ("units", "unit")
    route = f"/v1/companies/{company}/{resource}"
    body = {"code": "BOX", "name": "Box"} if pack else UNIT_BODY
    write = access(tenant_a, company, user, permission + ".manage", key="create")
    read = access(tenant_a, company, user, permission + ".read")
    created = await client.post(route, json=body, headers=write)
    assert created.status_code == 201, created.text
    object_route = created.headers["location"]
    result = created.json()
    assert result["row_version"] == 1 and result["is_active"] is True
    if not pack:
        assert result["quantity_increment"] == "1.0000"
    assert (await client.get(object_route, headers=read)).json() == result
    repeated = await client.post(route, json=body, headers=write)
    assert repeated.json() == result and repeated.headers["Idempotency-Replayed"] == "true"
    assert (
        await client.post(route, json={**body, "name": "Other"}, headers=write)
    ).status_code == 422
    assert (
        await client.post(route, json=body, headers={**write, "Idempotency-Key": "duplicate"})
    ).status_code == 409
    updated = await client.patch(
        object_route,
        json={"expected_version": 1, "name": "Renamed"},
        headers={**write, "Idempotency-Key": "update"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Renamed" and updated.json()["row_version"] == 2
    stale = await client.patch(
        object_route,
        json={"expected_version": 1, "name": "Stale"},
        headers={**write, "Idempotency-Key": "stale"},
    )
    assert stale.status_code == 409
    noop = await client.patch(
        object_route,
        json={"expected_version": 2, "name": " Renamed "},
        headers={**write, "Idempotency-Key": "noop"},
    )
    assert noop.status_code == 200 and noop.json()["row_version"] == 2
    for action, version in [("deactivate", 2), ("activate", 3)]:
        result_action = await client.post(
            object_route + "/" + action,
            json={"expected_version": version},
            headers={**write, "Idempotency-Key": action},
        )
        assert result_action.status_code == 200, result_action.text
        assert result_action.json()["is_active"] is (action == "activate")
    listed = await client.get(route, headers=read)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 1
    assert "created_at" not in listed.json()["items"][0]
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert len(list(await db.scalars(select(Outbox)))) == 4
            receipts = list(await db.scalars(select(IdempotencyKey)))
            assert len(receipts) == 5
            assert all(
                row.response_body is not None and set(row.response_body) == {"id", "changed"}
                for row in receipts
            )


@pytest.mark.parametrize("pack", [False, True])
async def test_master_list_filters_search_sort_and_cursor_binding(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    pack: bool,
) -> None:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    resource, permission = ("pack-types", "pack_type") if pack else ("units", "unit")
    route = f"/v1/companies/{company}/{resource}"
    read = access(tenant_a, company, user, permission + ".read")
    for number, name in enumerate(["Alpha", "Alpha", "A% literal", "Beta"]):
        body: dict[str, Any] = {"code": f"P{number}", "name": name}
        if not pack:
            body = {**UNIT_BODY, **body}
        result = await client.post(
            route,
            json=body,
            headers=access(tenant_a, company, user, permission + ".manage", key=f"create-{number}"),
        )
        assert result.status_code == 201, result.text
    first = await client.get(route, params={"limit": 1, "q": "Al", "sort": "-name"}, headers=read)
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["page"]["has_more"] is True and len(data["items"]) == 1
    cursor = data["page"]["next_cursor"]
    second = await client.get(
        route, params={"limit": 1, "q": "Al", "sort": "-name", "cursor": cursor}, headers=read
    )
    assert second.status_code == 200 and second.json()["page"]["has_more"] is False
    assert second.json()["items"][0]["id"] != data["items"][0]["id"]
    literal = await client.get(route, params={"q": "A%"}, headers=read)
    assert [row["name"] for row in literal.json()["items"]] == ["A% literal"]
    exact = await client.get(route, params={"code": "P3", "is_active": "true"}, headers=read)
    assert [row["name"] for row in exact.json()["items"]] == ["Beta"]
    bad_queries: list[dict[str, Any]] = [
        {"limit": 0},
        {"limit": 201},
        {"offset": 1},
        {"sort": "symbol"},
        {"q": "Al", "limit": 1, "sort": "name", "cursor": cursor},
        {"cursor": "tampered"},
        {"include_total": "true"},
    ]
    for query in bad_queries:
        assert (await client.get(route, params=query, headers=read)).status_code == 422
    assert (await client.get(route + "?limit=1&limit=2", headers=read)).status_code == 422


async def test_unit_authority_denials_are_atomic_and_replay_uses_current_fields(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/units"
    write = access(tenant_a, company, user, "unit.manage", key="create")
    read = access(tenant_a, company, user, "unit.read")
    created = await client.post(route, json=UNIT_BODY, headers=write)
    assert created.status_code == 201
    object_route = created.headers["location"]
    await seed_context(factory, tenant_a, company, user, (policy(user, "name", "read"),), version=3)
    replay = await client.post(route, json=UNIT_BODY, headers=write)
    assert replay.status_code == 201 and "name" not in replay.json()
    assert "name" not in (await client.get(object_route, headers=read)).json()
    listed = await client.get(route, headers=read)
    assert "name" not in listed.json()["items"][0]
    assert (await client.get(route, params={"sort": "name"}, headers=read)).status_code == 403
    assert (await client.get(route, params={"q": "Ea"}, headers=read)).status_code == 403
    await seed_context(
        factory, tenant_a, company, user, (policy(user, "name", "write"),), version=4
    )
    assert (await client.post(route, json=UNIT_BODY, headers=write)).status_code == 403
    denied = await client.patch(
        object_route,
        json={"expected_version": 1, "name": "Denied"},
        headers={**write, "Idempotency-Key": "deny-update"},
    )
    assert denied.status_code == 403
    no_change = await client.patch(
        object_route,
        json={"expected_version": 1, "name": "Each"},
        headers={**write, "Idempotency-Key": "same-name"},
    )
    assert no_change.status_code == 200
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert len(list(await db.scalars(select(Outbox)))) == 1
            assert len(list(await db.scalars(select(IdempotencyKey)))) == 2


@pytest.mark.parametrize("pack", [False, True])
async def test_master_rejects_bad_scope_stale_source_and_invalid_inputs(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    pack: bool,
) -> None:
    company, foreign_company, other, user = uuid7(), uuid7(), uuid7(), uuid7()
    for tenant, target in [(tenant_a, company), (tenant_a, other), (tenant_b, foreign_company)]:
        await seed_context(factory, tenant, target, user)
    resource, permission = ("pack-types", "pack_type") if pack else ("units", "unit")
    route = f"/v1/companies/{company}/{resource}"
    write = access(tenant_a, company, user, permission + ".manage", key="create")
    read = access(tenant_a, company, user, permission + ".read")
    body = {"code": "BOX", "name": "Box"} if pack else UNIT_BODY
    assert (await client.get(route)).status_code == 401
    assert (
        await client.post(route, json=body, headers={"Idempotency-Key": "anonymous"})
    ).status_code == 401
    assert (await client.post(route, json=body, headers=read)).status_code == 422
    assert (
        await client.post(route, json=body, headers={**read, "Idempotency-Key": "no-perm"})
    ).status_code == 403
    created = await client.post(route, json=body, headers=write)
    assert created.status_code == 201
    object_id = created.json()["id"]
    for tenant, target, expected in [(tenant_a, other, 403), (tenant_b, foreign_company, 404)]:
        scoped = access(tenant, target, user, permission + ".read")
        assert (
            await client.get(f"/v1/companies/{target}/{resource}/{object_id}", headers=scoped)
        ).status_code == expected
        assert (await client.get(f"/v1/companies/{target}/{resource}", headers=scoped)).json()[
            "items"
        ] == []
    for changes in [{"name": " "}, {"name": "x\n"}, {"extra": 1}, {"code": "lower"}]:
        assert (
            await client.post(route, json={**body, **cast(dict[str, Any], changes)}, headers=write)
        ).status_code == 422
    object_route = created.headers["location"]
    for changes in [{"name": None}, {"expected_version": True}, {"is_active": False}]:
        assert (
            await client.patch(
                object_route,
                json={"expected_version": 1, **cast(dict[str, Any], changes)},
                headers=write,
            )
        ).status_code == 422
    assert (await client.post(route + "?bad=1", json=body, headers=write)).status_code == 422
    assert (await client.get(object_route + "?bad=1", headers=read)).status_code == 422
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            checkpoint = await db.scalar(
                select(ProjectionCheckpoint).where(ProjectionCheckpoint.company_id == company)
            )
            assert checkpoint is not None
            checkpoint.expires_at = utcnow() - dt.timedelta(seconds=1)
    assert (await client.get(route, headers=read)).status_code == 503
    assert (await client.post(route, json=body, headers=write)).status_code == 503


async def test_unit_precision_and_used_definition_cannot_change(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/units"
    write = access(tenant_a, company, user, "unit.manage", key="create")
    for changes in [
        {"quantity_increment": 0.5},
        {"quantity_increment": "0"},
        {"quantity_increment": "0.1"},
        {"decimal_places": 5},
        {"decimal_places": True},
        {"quantity_increment": "0.00001"},
    ]:
        assert (
            await client.post(
                route, json={**UNIT_BODY, **cast(dict[str, Any], changes)}, headers=write
            )
        ).status_code == 422
    created = await client.post(route, json=UNIT_BODY, headers=write)
    object_route = created.headers["location"]
    object_id = uuid.UUID(created.json()["id"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                UnitConversion(
                    tenant_id=tenant_a,
                    company_id=company,
                    from_unit_id=object_id,
                    canonical_unit_id=object_id,
                    numerator=1,
                    denominator=1,
                )
            )
    blocked = await client.patch(
        object_route,
        json={"expected_version": 1, "decimal_places": 1},
        headers={**write, "Idempotency-Key": "referenced"},
    )
    assert blocked.status_code == 409
    assert (
        await client.post(
            object_route + "/deactivate",
            json={"expected_version": 1},
            headers={**write, "Idempotency-Key": "deactivate"},
        )
    ).status_code == 409
