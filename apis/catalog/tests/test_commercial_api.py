from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import CatalogPolicyState, Country, Outbox, State
from tests.commercial_factories import auth, reference_data
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import create


def command_headers(current: dict[str, str]) -> dict[str, str]:
    return {**current, "Idempotency-Key": str(uuid7())}


@pytest.mark.parametrize(
    "path", ["brands", "manufacturers", "brand-series", "manufacturer-sites", "product-types"]
)
async def test_commercial_crud_contract(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    path: str,
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    extra: dict[str, Any] = {}
    if path in {"brand-series", "manufacturer-sites"}:
        parent_path, parent_field = (
            ("brands", "brand_id")
            if path == "brand-series"
            else ("manufacturers", "manufacturer_id")
        )
        parent = await create(
            client, company, current, parent_path, {"code": "P", "name": "Parent"}
        )
        assert parent.status_code == 201, parent.text
        extra[parent_field] = parent.json()["id"]
    if path == "manufacturer-sites":
        await reference_data(factory)
        extra.update(country_code="IN", state_code="IN-MH")
    if path == "product-types":
        extra["kind"] = "GOODS"
    route = f"/v1/companies/{company}/{path}"
    body = {"code": "A", "name": "Alpha", **extra}
    assert (await client.post(route, json=body)).status_code == 401
    denied = headers(company, tenant=tenant_a, user=user, permission="item.read")
    assert (await client.post(route, headers=command_headers(denied), json=body)).status_code == 403
    receipt = command_headers(current)
    response = await client.post(route, headers=receipt, json=body)
    assert response.status_code == 201, response.text
    first = response.json()
    replay = await client.post(route, headers=receipt, json=body)
    assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == first
    assert (await create(client, company, current, path, body)).status_code == 409
    assert (
        await client.post(route, headers=receipt, json={**body, "name": "Different"})
    ).status_code == 422
    assert (
        await create(client, company, current, path, {**body, "code": "B", "name": "Beta"})
    ).status_code == 201
    page = await client.get(route, headers=current, params={"limit": 1, "sort": "-code"})
    assert page.status_code == 200, page.text
    assert page.json()["items"][0]["code"] == "B"
    assert not ({"custom_fields", "party_id", "owner_party_id"} & page.json()["items"][0].keys())
    next_page = await client.get(
        route,
        headers=current,
        params={"limit": 1, "sort": "-code", "cursor": page.json()["page"]["next_cursor"]},
    )
    assert next_page.json()["items"][0]["code"] == "A"
    assert (await client.get(route, headers=current, params={"q": "Al"})).json()["items"][0][
        "id"
    ] == first["id"]
    for query in ("limit=0", "unknown=x", "sort=custom_fields", "code=A&code=B"):
        assert (await client.get(route + "?" + query, headers=current)).status_code == 422
    detail = route + "/" + first["id"]
    assert (await client.get(detail, headers=current)).status_code == 200
    other_company = uuid7()
    other = await auth(factory, tenant_a, other_company, user)
    assert (
        await client.get(detail.replace(str(company), str(other_company)), headers=other)
    ).status_code == 403
    alien = await auth(factory, tenant_b, company, user)
    assert (await client.get(detail, headers=alien)).status_code == 404
    changed = await client.patch(
        detail, headers=command_headers(current), json={"expected_version": 1, "name": "Renamed"}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["row_version"] == 2
    assert (
        await client.patch(
            detail, headers=command_headers(current), json={"expected_version": 1, "name": "Stale"}
        )
    ).status_code == 409
    assert (
        await client.patch(
            detail, headers=command_headers(current), json={"expected_version": 2, "name": None}
        )
    ).status_code == 422
    noop = await client.patch(
        detail, headers=command_headers(current), json={"expected_version": 2, "name": "Renamed"}
    )
    assert noop.json()["row_version"] == 2
    for action, version in (("deactivate", 2), ("activate", 3)):
        result = await client.post(
            detail + "/" + action,
            headers=command_headers(current),
            json={"expected_version": version},
        )
        assert result.status_code == 200, result.text
        assert result.json()["is_active"] is (action == "activate")
    if extra:
        field = next(iter(extra))
        listed = await client.get(route, headers=current, params={field: extra[field]})
        assert listed.status_code == 200 and len(listed.json()["items"]) == 2
    with tenant_scope(tenant_a):
        async with factory() as db:
            events = list(
                await db.scalars(select(Outbox).where(Outbox.event_type.like("catalog.%")))
            )
            assert all(event.payload["company_id"] == str(company) for event in events)


async def test_brand_hierarchy_and_lifecycle(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    root = (
        await create(client, company, current, "brands", {"code": "ROOT", "name": "Root"})
    ).json()
    child = (
        await create(
            client,
            company,
            current,
            "brands",
            {"code": "CHILD", "name": "Child", "parent_brand_id": root["id"]},
        )
    ).json()
    base = f"/v1/companies/{company}/brands/"
    cycle = await client.post(
        base + root["id"] + "/reparent",
        headers=command_headers(current),
        json={
            "expected_version": 1,
            "expected_generation": child["policy_generation"],
            "parent_brand_id": child["id"],
        },
    )
    assert cycle.status_code == 422, cycle.text
    for suffix, body in [
        ("/deactivate", {"expected_version": 1}),
        ("", {"expected_version": 1, "code": "RENAMED"}),
    ]:
        result = await client.request(
            "POST" if suffix else "PATCH",
            base + root["id"] + suffix,
            headers=command_headers(current),
            json=body,
        )
        assert result.status_code == 409, result.text
    stale = await client.post(
        base + child["id"] + "/reparent",
        headers=command_headers(current),
        json={"expected_version": 1, "expected_generation": 1, "parent_brand_id": None},
    )
    assert stale.status_code == 409
    moved = await client.post(
        base + child["id"] + "/reparent",
        headers=command_headers(current),
        json={
            "expected_version": 1,
            "expected_generation": child["policy_generation"],
            "parent_brand_id": None,
        },
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["parent_brand_id"] is None
    inactive = await client.post(
        base + root["id"] + "/deactivate",
        headers=command_headers(current),
        json={"expected_version": 1},
    )
    assert inactive.status_code == 200
    for path, extra in [
        ("brands", {"parent_brand_id": root["id"]}),
        ("brand-series", {"brand_id": root["id"]}),
    ]:
        assert (
            await create(client, company, current, path, {"code": "NEW", "name": "New", **extra})
        ).status_code == 409
    assert (
        await client.post(
            base + root["id"] + "/reparent",
            headers=command_headers(current),
            json={
                "expected_version": 2,
                "expected_generation": inactive.json()["policy_generation"],
                "parent_brand_id": None,
            },
        )
    ).status_code == 409


@pytest.mark.parametrize(
    ("path", "field"), [("brands", "owner_party_id"), ("manufacturers", "party_id")]
)
async def test_party_dependency_is_explicit_and_rollback_atomic(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    path: str,
    field: str,
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    failed = await create(
        client, company, current, path, {"code": "P", "name": "Party", field: str(uuid7())}
    )
    assert failed.status_code == 503 and failed.json()["error"]["code"] == "source_unavailable"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Outbox.id))) == 0
            assert (
                await db.scalar(
                    select(CatalogPolicyState).where(CatalogPolicyState.company_id == company)
                )
                is None
            )
    valid = await create(client, company, current, path, {"code": "P", "name": "Party"})
    assert valid.status_code == 201
    update = await client.patch(
        f"/v1/companies/{company}/{path}/{valid.json()['id']}",
        headers=command_headers(current),
        json={"expected_version": 1, field: str(uuid7())},
    )
    assert update.status_code == 503


async def test_site_country_state_and_retired_reference(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    await reference_data(factory)
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    maker = (
        await create(client, company, current, "manufacturers", {"code": "M", "name": "Maker"})
    ).json()
    body = {
        "code": "SITE",
        "name": "Site",
        "manufacturer_id": maker["id"],
        "country_code": "IN",
        "state_code": "US-CA",
    }
    assert (await create(client, company, current, "manufacturer-sites", body)).status_code == 422
    valid = await create(
        client, company, current, "manufacturer-sites", {**body, "state_code": "IN-MH"}
    )
    assert valid.status_code == 201, valid.text
    route = f"/v1/companies/{company}/manufacturer-sites/{valid.json()['id']}"
    async with factory.begin() as db:
        state = await db.get(State, "IN-MH")
        assert state is not None
        state.is_active = False
    assert (
        await client.patch(
            route, headers=command_headers(current), json={"expected_version": 1, "name": "Renamed"}
        )
    ).status_code == 200
    assert (
        await client.post(
            route + "/deactivate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 200
    assert (
        await client.post(
            route + "/activate", headers=command_headers(current), json={"expected_version": 3}
        )
    ).status_code == 422
    assert (
        await client.patch(
            route,
            headers=command_headers(current),
            json={"expected_version": 3, "state_code": None},
        )
    ).status_code == 200
    async with factory.begin() as db:
        country = await db.get(Country, "IN")
        assert country is not None
        country.is_active = False
    assert (
        await client.post(
            route + "/activate", headers=command_headers(current), json={"expected_version": 4}
        )
    ).status_code == 422


@pytest.mark.parametrize(
    ("path", "entity"),
    [("brands", "brand"), ("manufacturers", "manufacturer"), ("product-types", "product_type")],
)
async def test_commercial_custom_fields_and_denies(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    path: str,
    entity: str,
) -> None:
    company, user = uuid7(), uuid7()
    original = all_facts(company, user)
    facts = tuple(
        SnapshotRecord(
            kind=r.kind,
            id=r.id,
            data={
                **r.data,
                "entity_type": "catalog." + entity,
                **({"is_required": True} if r.kind == "field_config" else {}),
            },
        )
        if r.kind in {"custom_definition", "field_config"}
        else r
        for r in original
    )
    current = await auth(factory, tenant_a, company, user, facts=facts)
    body = {
        "code": "C",
        "name": "Custom",
        **({"kind": "GOODS"} if entity == "product_type" else {}),
    }
    assert (await create(client, company, current, path, body)).status_code == 422
    valid = await create(
        client, company, current, path, {**body, "custom_fields": {"cf_note": "Private"}}
    )
    assert valid.status_code == 201, valid.text
    route = f"/v1/companies/{company}/{path}/{valid.json()['id']}"
    updated = await client.patch(
        route,
        headers=command_headers(current),
        json={"expected_version": 1, "custom_fields": {"cf_note": "Changed"}},
    )
    assert updated.status_code == 200 and updated.json()["custom_fields"]["cf_note"] == "Changed"
    base = next(r for r in original if r.kind == "field_policy")
    denies = tuple(
        SnapshotRecord(
            kind="field_policy",
            id=uuid7(),
            data={
                **base.data,
                "entity_type": "catalog." + entity,
                "subject_type": "user",
                "subject_id": str(user),
                "access": access,
                "field_key": field,
            },
        )
        for access, field in [("read", "custom_field:cf_note"), ("write", "name"), ("read", "code")]
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, *denies))
    detail = await client.get(route, headers=current)
    assert detail.json()["custom_fields"] == {} and "code" not in detail.json()
    assert (
        await client.patch(
            route,
            headers=command_headers(current),
            json={"expected_version": 2, "name": "Forbidden"},
        )
    ).status_code == 403
    assert (
        await client.get(route.rsplit("/", 1)[0], headers=current, params={"code": "C"})
    ).status_code == 403
