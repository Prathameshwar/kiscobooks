from __future__ import annotations

import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import HandlingProfileRevision, IdempotencyKey, Outbox
from tests.handling_factories import auth
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_commercial_api import command_headers


async def setup_profile(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str], str]:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant, company, user)
    result = await client.post(
        f"/v1/companies/{company}/handling-profiles",
        headers=command_headers(current),
        json={"code": "STANDARD", "name": "Standard handling"},
    )
    assert result.status_code == 201, result.text
    return (
        company,
        user,
        current,
        f"/v1/companies/{company}/handling-profiles/" + result.json()["id"],
    )


async def test_handling_every_endpoint_requires_auth_and_company_scope(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, user, current, master = await setup_profile(client, factory, tenant_a)
    route, revisions = master.rsplit("/", 1)[0], master + "/revisions"
    payload = {"temperature_min": "2", "temperature_max": "8", "temperature_unit": "CELSIUS"}
    created = await client.post(revisions, headers=command_headers(current), json=payload)
    assert created.status_code == 201
    detail = revisions + "/" + created.json()["id"]
    requests = (
        ("GET", route, None),
        ("POST", route, {"code": "SECOND", "name": "Second"}),
        ("GET", master, None),
        ("PATCH", master, {"expected_version": 1, "name": "Changed"}),
        ("POST", master + "/activate", {"expected_version": 1}),
        ("POST", master + "/deactivate", {"expected_version": 1}),
        ("GET", revisions, None),
        ("POST", revisions, payload),
        ("GET", detail, None),
        ("PATCH", detail, {"expected_version": 1, "temperature_max": "9"}),
        ("POST", detail + "/publish", {"expected_version": 1}),
    )
    forbidden = headers(company, tenant=tenant_a, user=user, permission="unit.read")
    for method, path, body in requests:
        for auth_headers, expected in (({}, 401), (forbidden, 403)):
            response = await client.request(
                method, path, headers={**auth_headers, "Idempotency-Key": str(uuid7())}, json=body
            )
            assert response.status_code == expected, (method, path, response.text)
    other_company = uuid7()
    other = await auth(factory, tenant_a, other_company, user)
    for method, path, body in requests:
        if path == route:
            continue
        response = await client.request(
            method,
            path.replace(str(company), str(other_company)),
            headers=command_headers(other),
            json=body,
        )
        assert response.status_code == 403, response.text
    other_parent = await client.post(
        route, headers=command_headers(current), json={"code": "SECOND", "name": "Second"}
    )
    wrong_parent = detail.replace(master.rsplit("/", 1)[-1], other_parent.json()["id"])
    assert (await client.get(wrong_parent, headers=current)).status_code == 403
    alien = await auth(factory, tenant_b, company, user)
    assert (await client.get(detail, headers=alien)).status_code == 404


async def test_handling_field_policy_atomicity_replay_and_read_guards(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, _, master = await setup_profile(client, factory, tenant_a)
    facts = all_facts(company, user)
    source = next(row for row in facts if row.kind == "field_policy")
    policy = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **source.data,
            "entity_type": "catalog.handling_profile_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "temperature_max",
            "access": "write",
            "condition": {"field": "temperature_max", "cmp": "gt", "value": "30"},
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, policy))
    revisions = master + "/revisions"
    payload = {"temperature_max": "60", "temperature_unit": "CELSIUS", "fragile": True}
    receipt = command_headers(current)
    assert (await client.post(revisions, headers=receipt, json=payload)).status_code == 403
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(HandlingProfileRevision.id))) == 0
            assert await db.scalar(select(func.count(IdempotencyKey.id))) == 1
            assert await db.scalar(select(func.count(Outbox.id))) == 1
    payload["temperature_max"] = "30"
    allowed = await client.post(revisions, headers=receipt, json=payload)
    assert allowed.status_code == 201, allowed.text
    assert (await client.post(revisions, headers=receipt, json=payload)).status_code == 201
    detail = revisions + "/" + allowed.json()["id"]
    deny = SnapshotRecord(
        kind="field_policy", id=policy.id, data={**policy.data, "condition": None}
    )
    current = await auth(factory, tenant_a, company, user, version=4, facts=(*facts, deny))
    assert (
        await client.post(revisions, headers={**receipt, **current}, json=payload)
    ).status_code == 403
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 403
    hidden = tuple(
        SnapshotRecord(
            kind="field_policy", id=uuid7(), data={**deny.data, "field_key": key, "access": "read"}
        )
        for key in ("fragile", "revision", "published_at", "instructions")
    )
    current = await auth(factory, tenant_a, company, user, version=5, facts=(*facts, *hidden))
    page = await client.get(revisions, headers=current)
    assert page.status_code == 200 and "fragile" not in page.json()["items"][0]
    assert "instructions" not in (await client.get(detail, headers=current)).json()
    for query in ({"fragile": "true"}, {"sort": "revision"}, {"published": "true"}):
        assert (await client.get(revisions, headers=current, params=query)).status_code == 403
    metadata = await client.get(
        f"/v1/companies/{company}/entities/catalog.handling_profile_revision/field-set",
        headers=current,
    )
    assert metadata.status_code == 200
    fields = {entry["key"]: entry for entry in metadata.json()["fields"]}
    assert fields["profile_id"]["writable"] is False and "revision" not in fields
    membership = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={**deny.data, "field_key": "profile_id", "access": "read"},
    )
    current = await auth(factory, tenant_a, company, user, version=6, facts=(*facts, membership))
    for path in (revisions, detail):
        assert (await client.get(path, headers=current)).status_code == 403
