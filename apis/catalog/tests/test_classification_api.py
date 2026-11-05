from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.classification import CatalogPolicyState, ItemGroupParent
from catalog.tasks.projections import activate_snapshot
from tests.source_factories import all_facts, snapshot
from tests.test_api import headers


async def setup_source(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    *,
    version: int = 2,
    facts: tuple[SnapshotRecord, ...] | None = None,
) -> dict[str, str]:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(
                db, snapshot(tenant, company, facts or all_facts(company, user), version=version)
            )
    return headers(
        company,
        permission=[
            prefix + suffix
            for prefix in ("item_group", "item_category", "category_scheme")
            for suffix in (
                (".read", ".manage", ".move")
                if prefix != "category_scheme"
                else (".read", ".manage")
            )
        ],
        tenant=tenant,
        user=user,
    )


async def create(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    auth: dict[str, str],
    path: str,
    body: dict[str, Any],
) -> httpx.Response:
    return await client.post(
        f"/v1/companies/{company}/{path}",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json=body,
    )


async def test_conditional_parent_denies_evaluate_fresh_hierarchy_values(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    base = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **base.data,
            "entity_type": "catalog.item_group_parent",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "valid_from",
            "access": "write",
            "condition": {"field": "valid_from", "cmp": "lt", "value": "2020-01-01"},
        },
    )
    current = await setup_source(factory, tenant_a, company, user, facts=(*facts, deny))
    route = f"/v1/companies/{company}/item-groups"
    key = {**current, "Idempotency-Key": str(uuid7())}
    body = {"code": "CHILD", "name": "Child", "valid_from": "2020-01-01"}
    child = await client.post(route, headers=key, json=body)
    assert child.status_code == 201, child.text
    parent = await create(client, company, current, "item-groups", {**body, "code": "PARENT"})
    assert parent.status_code == 201, parent.text
    moved = await client.post(
        route + "/" + child.json()["id"] + "/reparent",
        headers={**current, "Idempotency-Key": str(uuid7())},
        json={
            "expected_version": 1,
            "expected_generation": parent.json()["policy_generation"],
            "effective_from": "2099-01-01",
            "parent_group_id": parent.json()["id"],
        },
    )
    assert moved.status_code == 200, moved.text
    denied = await create(
        client, company, current, "item-groups", {**body, "code": "OLD", "valid_from": "2019-01-01"}
    )
    assert denied.status_code == 403
    assert (await client.post(route, headers=key, json=body)).status_code == 403
    inactive = await create(client, company, current, "item-groups", {**body, "code": "INACTIVE"})
    assert inactive.status_code == 201
    retired = await client.post(
        route + "/" + inactive.json()["id"] + "/deactivate",
        headers={**current, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 1},
    )
    assert retired.status_code == 200
    rejected_move = await client.post(
        route + "/" + child.json()["id"] + "/reparent",
        headers={**current, "Idempotency-Key": str(uuid7())},
        json={
            "expected_version": 2,
            "expected_generation": retired.json()["policy_generation"],
            "effective_from": "2099-01-02",
            "parent_group_id": inactive.json()["id"],
        },
    )
    assert rejected_move.status_code == 409


@pytest.mark.parametrize(
    ("path", "extra"),
    [
        ("item-groups", {"valid_from": "2020-01-01"}),
        ("category-schemes", {"membership_mode": "SINGLE"}),
        ("item-categories", {}),
    ],
)
async def test_master_commands_lists_and_scopes(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    path: str,
    extra: dict[str, Any],
) -> None:
    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/{path}"
    if path == "item-categories":
        scheme = await create(
            client,
            company,
            auth,
            "category-schemes",
            {"code": "SCHEME", "name": "Scheme", "membership_mode": "MULTIPLE"},
        )
        assert scheme.status_code == 201, scheme.text
        extra = {"scheme_id": scheme.json()["id"]}
    body = {"code": "A", "name": "Alpha", **extra}
    command_headers = {**auth, "Idempotency-Key": str(uuid7())}
    assert (await client.post(route, json=body)).status_code == 401
    assert (
        await client.post(
            route,
            headers={
                **headers(company, permission="item.read", tenant=tenant_a, user=user),
                "Idempotency-Key": str(uuid7()),
            },
            json=body,
        )
    ).status_code == 403
    response = await client.post(route, headers=command_headers, json=body)
    assert response.status_code == 201, response.text
    first = response.json()
    replay = await client.post(route, headers=command_headers, json=body)
    assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == first
    assert (await create(client, company, auth, path, body)).status_code == 409
    assert (
        await client.post(route, headers=command_headers, json={**body, "name": "Different"})
    ).status_code == 422
    assert (
        await create(client, company, auth, path, {**body, "code": "B", "name": "Beta"})
    ).status_code == 201
    page = await client.get(route + "?limit=1&sort=-code", headers=auth)
    assert page.status_code == 200, page.text
    assert page.json()["items"][0]["code"] == "B"
    assert "custom_fields" not in page.json()["items"][0]
    cursor = page.json()["page"]["next_cursor"]
    next_page = await client.get(
        route, headers=auth, params={"limit": 1, "sort": "-code", "cursor": cursor}
    )
    assert next_page.json()["items"][0]["code"] == "A"
    assert (await client.get(route + "?q=Al", headers=auth)).json()["items"][0]["id"] == first["id"]
    for query in ("limit=0", "unknown=x", "sort=custom_fields", "code=A&code=B"):
        assert (await client.get(route + "?" + query, headers=auth)).status_code == 422
    detail = route + "/" + first["id"]
    assert (await client.get(detail, headers=auth)).status_code == 200
    wrong_company = uuid7()
    other_auth = await setup_source(factory, tenant_a, wrong_company, user)
    assert (
        await client.get(detail.replace(str(company), str(wrong_company)), headers=other_auth)
    ).status_code == 403
    other_tenant_auth = await setup_source(factory, tenant_b, company, user)
    assert (await client.get(detail, headers=other_tenant_auth)).status_code == 404
    updated = await client.patch(
        detail,
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 1, "name": "Updated"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["row_version"] == 2
    assert (
        await client.patch(
            detail,
            headers={**auth, "Idempotency-Key": str(uuid7())},
            json={"expected_version": 1, "name": "Stale"},
        )
    ).status_code == 409
    assert (
        await client.patch(
            detail,
            headers={**auth, "Idempotency-Key": str(uuid7())},
            json={"expected_version": 2, "name": None},
        )
    ).status_code == 422
    no_op = await client.patch(
        detail,
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 2, "name": "Updated"},
    )
    assert no_op.json()["row_version"] == 2
    for action, version in (("deactivate", 2), ("activate", 3)):
        result = await client.post(
            detail + "/" + action,
            headers={**auth, "Idempotency-Key": str(uuid7())},
            json={"expected_version": version},
        )
        assert result.status_code == 200, result.text
        assert result.json()["is_active"] is (action == "activate")


async def test_dated_group_reparent_rejects_cycles_and_preserves_history(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    general = await create(
        client,
        company,
        auth,
        "item-groups",
        {"code": "GENERAL", "name": "General", "valid_from": "1000-01-01"},
    )
    assert general.status_code == 201, general.text
    a = await create(
        client, company, auth, "item-groups", {"code": "A", "name": "A", "valid_from": "2020-01-01"}
    )
    assert a.status_code == 201, a.text
    b = await create(
        client,
        company,
        auth,
        "item-groups",
        {"code": "B", "name": "B", "valid_from": "2020-01-01", "parent_group_id": a.json()["id"]},
    )
    assert b.status_code == 201, b.text
    route = f"/v1/companies/{company}/item-groups/"
    generation = b.json()["policy_generation"]
    tomorrow = (dt.date.today() + dt.timedelta(days=10)).isoformat()
    move = {
        "expected_version": 1,
        "expected_generation": generation,
        "parent_group_id": b.json()["id"],
        "effective_from": tomorrow,
    }
    cycle = await client.post(
        route + a.json()["id"] + "/reparent",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json=move,
    )
    assert cycle.status_code == 422, cycle.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemGroupParent.id))) == 3
            assert await db.scalar(select(CatalogPolicyState.generation)) == generation
    changed = await client.post(
        route + b.json()["id"] + "/reparent",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={**move, "parent_group_id": general.json()["id"]},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["row_version"] == 2
    with tenant_scope(tenant_a):
        async with factory() as db:
            edges = list(
                await db.scalars(
                    select(ItemGroupParent)
                    .where(ItemGroupParent.group_id == uuid.UUID(b.json()["id"]))
                    .order_by(ItemGroupParent.valid_from)
                )
            )
            assert len(edges) == 2
            assert edges[0].valid_to == dt.date.fromisoformat(tomorrow) - dt.timedelta(days=1)
            assert str(edges[1].parent_group_id) == general.json()["id"]
    stale = await client.post(
        route + a.json()["id"] + "/reparent",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json=move,
    )
    assert stale.status_code == 409
    protected = await client.post(
        route + general.json()["id"] + "/deactivate",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 1},
    )
    assert protected.status_code == 409


async def test_category_reparent_checks_scheme_cycle_and_generation(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    scheme = await create(
        client,
        company,
        auth,
        "category-schemes",
        {"code": "S", "name": "S", "membership_mode": "SINGLE"},
    )
    other = await create(
        client,
        company,
        auth,
        "category-schemes",
        {"code": "O", "name": "O", "membership_mode": "MULTIPLE"},
    )
    a = await create(
        client,
        company,
        auth,
        "item-categories",
        {"code": "A", "name": "A", "scheme_id": scheme.json()["id"]},
    )
    assert a.status_code == 201, a.text
    b = await create(
        client,
        company,
        auth,
        "item-categories",
        {"code": "B", "name": "B", "scheme_id": scheme.json()["id"], "parent_id": a.json()["id"]},
    )
    assert b.status_code == 201, b.text
    invalid = await create(
        client,
        company,
        auth,
        "item-categories",
        {"code": "C", "name": "C", "scheme_id": other.json()["id"], "parent_id": a.json()["id"]},
    )
    assert invalid.status_code == 422
    route = f"/v1/companies/{company}/item-categories/{a.json()['id']}/reparent"
    cycle = await client.post(
        route,
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "expected_version": 1,
            "expected_generation": b.json()["policy_generation"],
            "parent_id": b.json()["id"],
        },
    )
    assert cycle.status_code == 422, cycle.text
    moved = await client.post(
        route.replace(a.json()["id"], b.json()["id"]),
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "expected_version": 1,
            "expected_generation": b.json()["policy_generation"],
            "parent_id": None,
        },
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["parent_id"] is None


async def test_group_custom_fields_required_defaults_and_read_denies(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    rows = tuple(
        SnapshotRecord(
            kind=row.kind,
            id=row.id,
            data={
                **row.data,
                "entity_type": "catalog.item_group",
                **({"is_required": True} if row.kind == "field_config" else {}),
            },
        )
        if row.kind in {"custom_definition", "field_config"}
        else row
        for row in facts
    )
    auth = await setup_source(factory, tenant_a, company, user, facts=rows)
    missing = await create(
        client, company, auth, "item-groups", {"code": "A", "name": "A", "valid_from": "2020-01-01"}
    )
    assert missing.status_code == 422, missing.text
    valid = await create(
        client,
        company,
        auth,
        "item-groups",
        {
            "code": "A",
            "name": "A",
            "valid_from": "2020-01-01",
            "custom_fields": {"cf_note": "Private"},
        },
    )
    assert valid.status_code == 201, valid.text
    assert valid.json()["custom_fields"] == {"cf_note": "Private"}
    policy = next(row for row in facts if row.kind == "field_policy")
    denied = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.item_group",
            "field_key": "custom_field:cf_note",
            "access": "read",
            "subject_type": "user",
            "subject_id": str(user),
        },
    )
    auth = await setup_source(factory, tenant_a, company, user, version=3, facts=(*rows, denied))
    response = await client.get(
        f"/v1/companies/{company}/item-groups/{valid.json()['id']}", headers=auth
    )
    assert response.status_code == 200, response.text
    assert response.json()["custom_fields"] == {}
    assert "Private" not in response.text


async def test_group_dates_reject_values_outside_supported_mysql_range(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    response = await create(
        client,
        company,
        auth,
        "item-groups",
        {"code": "BAD_DATE", "name": "Bad date", "valid_from": "0999-12-31"},
    )
    assert response.status_code == 422


async def test_replayed_group_create_rechecks_conditional_parent_write_denies(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    auth = await setup_source(factory, tenant_a, company, user, facts=facts)
    route = f"/v1/companies/{company}/item-groups"
    body = {"code": "A", "name": "A", "valid_from": "2020-01-01"}
    command_headers = {**auth, "Idempotency-Key": str(uuid7())}
    created = await client.post(route, headers=command_headers, json=body)
    assert created.status_code == 201, created.text
    template = next(row for row in facts if row.kind == "field_policy")
    policy = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **template.data,
            "entity_type": "catalog.item_group_parent",
            "field_key": "parent_group_id",
            "subject_type": "user",
            "subject_id": str(user),
            "condition": {"field": "group_id", "cmp": "eq", "value": created.json()["id"]},
        },
    )
    await setup_source(factory, tenant_a, company, user, facts=(*facts, policy), version=3)
    replay = await client.post(route, headers=command_headers, json=body)
    assert replay.status_code == 403, replay.text


async def test_parent_history_is_paged_and_field_protected(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    auth = await setup_source(factory, tenant_a, company, user, facts=facts)
    created = await create(
        client, company, auth, "item-groups", {"code": "A", "name": "A", "valid_from": "2020-01-01"}
    )
    assert created.status_code == 201, created.text
    route = f"/v1/companies/{company}/item-groups/{created.json()['id']}/parents"
    history = await client.get(route + "?valid_at=2020-01-01&limit=1", headers=auth)
    assert history.status_code == 200, history.text
    assert len(history.json()["items"]) == 1
    assert history.json()["items"][0]["parent_group_id"] is None
    assert (await client.get(route + "?valid_at=2019-12-31", headers=auth)).json()["items"] == []
    assert (await client.get(route + "?q=hello", headers=auth)).status_code == 422
    template = next(row for row in facts if row.kind == "field_policy")
    policy = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **template.data,
            "entity_type": "catalog.item_group_parent",
            "field_key": "valid_from",
            "access": "read",
            "subject_type": "user",
            "subject_id": str(user),
        },
    )
    await setup_source(factory, tenant_a, company, user, facts=(*facts, policy), version=3)
    assert (await client.get(route + "?valid_at=2020-01-01", headers=auth)).status_code == 403
    protected = await client.get(route, headers=auth)
    assert protected.status_code == 200, protected.text
    assert "valid_from" not in protected.json()["items"][0]


async def test_general_seed_reruns_preserve_defaults_and_custom_values(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from catalog.seeds.classification import seed_general

    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    first = await seed_general(client, company, headers=auth)
    second = await seed_general(client, company, headers=auth)
    assert first == second
    route = f"/v1/companies/{company}/item-groups/{first}"
    changed = await client.patch(
        route,
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 1, "name": "General products"},
    )
    assert changed.status_code == 200, changed.text
    assert await seed_general(client, company, headers=auth) == first
    assert (await client.get(route, headers=auth)).json()["name"] == "General products"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemGroupParent.id))) == 1


@pytest.mark.parametrize("reset", ["never", "calendar_year", "month", "fiscal_year"])
async def test_group_auto_number_is_transactional_and_current_feature_gated(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    reset: str,
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    rows = tuple(
        SnapshotRecord(
            kind=row.kind,
            id=row.id,
            data={
                **row.data,
                "entity_type": "catalog.item_group",
                **(
                    {
                        "data_type": "auto_number",
                        "sequence_config": {
                            "prefix": "G-",
                            "padding": 3,
                            "start": 1,
                            "reset": reset,
                        },
                    }
                    if row.kind == "custom_definition"
                    else {}
                ),
            },
        )
        if row.kind in {"custom_definition", "field_config"}
        else row
        for row in facts
    )
    auth = await setup_source(factory, tenant_a, company, user, facts=rows)
    body = {"code": "A", "name": "A", "valid_from": "2020-01-01"}
    created = await create(client, company, auth, "item-groups", body)
    if reset == "fiscal_year":
        assert created.status_code == 409, created.text
        return
    assert created.status_code == 201, created.text
    assert created.json()["custom_fields"] == {"cf_note": "G-001"}
    second = await create(client, company, auth, "item-groups", {**body, "code": "B"})
    assert second.json()["custom_fields"] == {"cf_note": "G-002"}
    denied = await create(
        client,
        company,
        auth,
        "item-groups",
        {**body, "code": "C", "custom_fields": {"cf_note": "client-authored"}},
    )
    assert denied.status_code == 422


async def test_classification_dependencies_kinds_and_inactive_references(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    base = f"/v1/companies/{company}"
    a = await create(
        client, company, auth, "item-groups", {"code": "A", "name": "A", "valid_from": "2020-01-01"}
    )
    b = await create(
        client,
        company,
        auth,
        "item-groups",
        {
            "code": "B",
            "name": "B",
            "valid_from": "2020-01-01",
            "allowed_kind": "SERVICE",
            "parent_group_id": a.json()["id"],
        },
    )
    assert b.status_code == 201, b.text
    route = base + "/item-groups/" + a.json()["id"]

    async def patch(path: str, body: dict[str, Any]) -> httpx.Response:
        return await client.patch(
            path, headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
        )

    assert (await patch(route, {"expected_version": 1, "allowed_kind": "GOODS"})).status_code == 422
    assert (await patch(route, {"expected_version": 1, "allowed_kind": None})).status_code == 422
    assert (await patch(route, {"expected_version": 1, "code": "RENAMED"})).status_code == 409
    assert (
        await patch(route + "?unexpected=x", {"expected_version": 1, "name": "Changed"})
    ).status_code == 422
    c = await create(
        client, company, auth, "item-groups", {"code": "C", "name": "C", "valid_from": "2020-01-01"}
    )
    off = await client.post(
        base + "/item-groups/" + c.json()["id"] + "/deactivate",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 1},
    )
    assert off.status_code == 200
    invalid = await create(
        client,
        company,
        auth,
        "item-groups",
        {"code": "D", "name": "D", "valid_from": "2020-01-01", "parent_group_id": c.json()["id"]},
    )
    assert invalid.status_code == 409
    scheme = await create(
        client,
        company,
        auth,
        "category-schemes",
        {"code": "S", "name": "S", "membership_mode": "SINGLE"},
    )
    category = await create(
        client,
        company,
        auth,
        "item-categories",
        {"code": "C", "name": "C", "scheme_id": scheme.json()["id"]},
    )
    sub = await create(
        client,
        company,
        auth,
        "item-categories",
        {
            "code": "SUB",
            "name": "SUB",
            "scheme_id": scheme.json()["id"],
            "parent_id": category.json()["id"],
        },
    )
    assert sub.status_code == 201
    assert (
        await patch(
            base + "/category-schemes/" + scheme.json()["id"],
            {"expected_version": 1, "membership_mode": "MULTIPLE"},
        )
    ).status_code == 409
    assert (
        await patch(
            base + "/item-categories/" + category.json()["id"],
            {"expected_version": 1, "code": "OTHER"},
        )
    ).status_code == 409
    unused = await create(
        client,
        company,
        auth,
        "category-schemes",
        {"code": "OFF", "name": "Off", "membership_mode": "SINGLE"},
    )
    disabled = await client.post(
        base + "/category-schemes/" + unused.json()["id"] + "/deactivate",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 1},
    )
    assert disabled.status_code == 200
    invalid = await create(
        client,
        company,
        auth,
        "item-categories",
        {"code": "INVALID", "name": "Invalid", "scheme_id": unused.json()["id"]},
    )
    assert invalid.status_code == 409


async def test_custom_update_clears_and_search_readiness_gate(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    rows = tuple(
        SnapshotRecord(
            kind=row.kind, id=row.id, data={**row.data, "entity_type": "catalog.item_group"}
        )
        if row.kind in {"custom_definition", "field_config"}
        else row
        for row in facts
    )
    auth = await setup_source(factory, tenant_a, company, user, facts=rows)
    created = await create(
        client,
        company,
        auth,
        "item-groups",
        {"code": "A", "name": "A", "valid_from": "2020-01-01", "custom_fields": {"cf_note": "Old"}},
    )
    assert created.status_code == 201
    route = f"/v1/companies/{company}/item-groups/{created.json()['id']}"
    for version, value in [(1, "New"), (2, None)]:
        response = await client.patch(
            route,
            headers={**auth, "Idempotency-Key": str(uuid7())},
            json={"expected_version": version, "custom_fields": {"cf_note": value}},
        )
        assert response.status_code == 200, response.text
        assert response.json()["custom_fields"] == {"cf_note": value}
    searchable = tuple(
        SnapshotRecord(kind=row.kind, id=row.id, data={**row.data, "is_searchable": True})
        if row.kind == "custom_definition"
        else row
        for row in rows
    )
    await setup_source(factory, tenant_a, company, user, facts=searchable, version=3)
    blocked = await client.patch(
        route,
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 3, "custom_fields": {"cf_note": "Indexed"}},
    )
    assert blocked.status_code == 409


async def test_group_move_retries_boundaries_inactive_and_exhaustion(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from catalog.models.classification import ItemGroup

    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    a = await create(
        client, company, auth, "item-groups", {"code": "A", "name": "A", "valid_from": "2020-01-01"}
    )
    b = await create(
        client,
        company,
        auth,
        "item-groups",
        {"code": "B", "name": "B", "valid_from": "2020-01-01", "parent_group_id": a.json()["id"]},
    )
    path = f"/v1/companies/{company}/item-groups/{b.json()['id']}/reparent"
    body = {
        "expected_version": 1,
        "expected_generation": b.json()["policy_generation"],
        "effective_from": (dt.date.today() + dt.timedelta(days=10)).isoformat(),
        "parent_group_id": a.json()["id"],
    }
    same = await client.post(path, headers={**auth, "Idempotency-Key": str(uuid7())}, json=body)
    assert same.status_code == 200 and same.json()["row_version"] == 1
    invalid = await client.post(
        path,
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={**body, "parent_group_id": None, "effective_from": "2020-01-01"},
    )
    assert invalid.status_code == 409
    rooted = await client.post(
        path,
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={**body, "parent_group_id": None},
    )
    assert rooted.status_code == 200, rooted.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            # Simulate a recovered/corrupt source-independent hierarchy and the
            # documented generation boundary; commands must leave it unchanged.
            state = await db.scalar(select(CatalogPolicyState))
            assert state is not None
            state.generation = 2**63 - 1
    exhausted = await client.patch(
        path.removesuffix("/reparent"),
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 2, "name": "Changed"},
    )
    assert exhausted.status_code == 409
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            state = await db.scalar(select(CatalogPolicyState))
            assert state is not None
            state.generation = 10
            row = await db.get(ItemGroup, uuid.UUID(b.json()["id"]))
            assert row is not None
            row.is_active = False
    inactive = await client.post(
        path,
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={**body, "expected_version": 2, "expected_generation": 10},
    )
    assert inactive.status_code == 409


async def test_category_moves_reject_inactive_and_foreign_scheme_parents(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    scheme = await create(
        client,
        company,
        auth,
        "category-schemes",
        {"code": "S", "name": "S", "membership_mode": "SINGLE"},
    )
    other = await create(
        client,
        company,
        auth,
        "category-schemes",
        {"code": "O", "name": "O", "membership_mode": "SINGLE"},
    )
    a = await create(
        client,
        company,
        auth,
        "item-categories",
        {"code": "A", "name": "A", "scheme_id": scheme.json()["id"]},
    )
    b = await create(
        client,
        company,
        auth,
        "item-categories",
        {"code": "B", "name": "B", "scheme_id": other.json()["id"]},
    )
    route = f"/v1/companies/{company}/item-categories/{a.json()['id']}"
    invalid = await client.post(
        route + "/reparent",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "expected_version": 1,
            "expected_generation": b.json()["policy_generation"],
            "parent_id": b.json()["id"],
        },
    )
    assert invalid.status_code == 422
    c = await create(
        client,
        company,
        auth,
        "item-categories",
        {"code": "C", "name": "C", "scheme_id": scheme.json()["id"]},
    )
    off = await client.post(
        route.replace(a.json()["id"], c.json()["id"]) + "/deactivate",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 1},
    )
    assert off.status_code == 200
    invalid = await client.post(
        route + "/reparent",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "expected_version": 1,
            "expected_generation": off.json()["policy_generation"],
            "parent_id": c.json()["id"],
        },
    )
    assert invalid.status_code == 422


async def test_general_reparent_failure_rolls_back_hierarchy_and_audit(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from catalog.models import Outbox

    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    general = await create(
        client,
        company,
        auth,
        "item-groups",
        {"code": "GENERAL", "name": "General", "valid_from": "1000-01-01"},
    )
    root = await create(
        client,
        company,
        auth,
        "item-groups",
        {"code": "ROOT", "name": "Root", "valid_from": "1000-01-01"},
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            before = await db.scalar(select(func.count(Outbox.id)))
    response = await client.post(
        f"/v1/companies/{company}/item-groups/{general.json()['id']}/reparent",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "expected_version": 1,
            "expected_generation": root.json()["policy_generation"],
            "effective_from": (dt.date.today() + dt.timedelta(days=10)).isoformat(),
            "parent_group_id": root.json()["id"],
        },
    )
    assert response.status_code == 409, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Outbox.id))) == before
            rows = list(
                await db.scalars(
                    select(ItemGroupParent).where(
                        ItemGroupParent.group_id == uuid.UUID(general.json()["id"])
                    )
                )
            )
            assert len(rows) == 1 and rows[0].valid_to is None and rows[0].parent_group_id is None


async def test_children_browse_is_dated_scoped_and_cursor_bound(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    auth = await setup_source(factory, tenant_a, company, user, facts=facts)
    root = await create(
        client,
        company,
        auth,
        "item-groups",
        {"code": "ROOT", "name": "Root", "valid_from": "2020-01-01"},
    )
    second = await create(
        client,
        company,
        auth,
        "item-groups",
        {"code": "OTHER", "name": "Other", "valid_from": "2020-01-01"},
    )
    for code in ("A", "B"):
        created = await create(
            client,
            company,
            auth,
            "item-groups",
            {
                "code": code,
                "name": code,
                "valid_from": "2021-01-01",
                "parent_group_id": root.json()["id"],
            },
        )
        assert created.status_code == 201
    route = f"/v1/companies/{company}/item-groups/{root.json()['id']}/children"
    assert (await client.get(route, headers=auth)).status_code == 422
    assert (await client.get(route + "?valid_at=2020-12-31", headers=auth)).json()["items"] == []
    first = await client.get(route, headers=auth, params={"valid_at": "2021-01-01", "limit": 1})
    assert first.status_code == 200, first.text
    assert first.json()["items"][0]["code"] == "A"
    cursor = first.json()["page"]["next_cursor"]
    other = await client.get(
        route.replace(root.json()["id"], second.json()["id"]),
        headers=auth,
        params={"valid_at": "2021-01-01", "limit": 1, "cursor": cursor},
    )
    assert other.status_code == 422
    next_page = await client.get(
        route, headers=auth, params={"valid_at": "2021-01-01", "limit": 1, "cursor": cursor}
    )
    assert next_page.json()["items"][0]["code"] == "B"
    template = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **template.data,
            "entity_type": "catalog.item_group_parent",
            "field_key": "parent_group_id",
            "access": "read",
            "subject_type": "user",
            "subject_id": str(user),
        },
    )
    await setup_source(factory, tenant_a, company, user, facts=(*facts, deny), version=3)
    assert (await client.get(route + "?valid_at=2021-01-01", headers=auth)).status_code == 403
