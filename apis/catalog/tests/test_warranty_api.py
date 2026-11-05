from __future__ import annotations

import uuid
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import IdempotencyKey, Outbox, WarrantyPolicyRevision
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.warranty_factories import auth


async def setup_policy(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str], str]:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant, company, user)
    result = await client.post(
        f"/v1/companies/{company}/warranty-policies",
        headers=command_headers(current),
        json={"code": "STANDARD", "name": "Standard warranty"},
    )
    assert result.status_code == 201, result.text
    return (
        company,
        user,
        current,
        f"/v1/companies/{company}/warranty-policies/" + result.json()["id"],
    )


async def test_warranty_workflow_calendar_limits_and_history(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, _, current, master = await setup_policy(client, factory, tenant_a)
    route, revisions = master.rsplit("/", 1)[0], master + "/revisions"
    rename = await client.patch(
        master, headers=command_headers(current), json={"expected_version": 1, "code": "RETAIL"}
    )
    assert rename.status_code == 200 and rename.json()["row_version"] == 2
    assert (await client.get(master, headers=current)).json()["code"] == "RETAIL"
    payload: dict[str, Any] = {
        "duration": 12,
        "duration_unit": "MONTHS",
        "coverage_description": "  Parts\nLabour  ",
    }
    receipt = command_headers(current)
    created = await client.post(revisions, headers=receipt, json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["coverage_description"] == "Parts\nLabour"
    assert created.json()["start_trigger"] == "SALE" and created.json()["revision"] == 1
    assert (await client.post(revisions, headers=receipt, json=payload)).headers[
        "Idempotency-Replayed"
    ] == "true"
    detail = revisions + "/" + created.json()["id"]
    assert (await client.get(detail, headers=current)).json()["duration_unit"] == "MONTHS"
    assert (
        await client.patch(
            master, headers=command_headers(current), json={"expected_version": 2, "code": "RENAME"}
        )
    ).status_code == 409
    renamed = await client.patch(
        master,
        headers=command_headers(current),
        json={"expected_version": 2, "name": "Retail coverage"},
    )
    assert renamed.status_code == 200 and renamed.json()["row_version"] == 3
    for action, version in (("deactivate", 3), ("activate", 4)):
        response = await client.post(
            master + "/" + action,
            headers=command_headers(current),
            json={"expected_version": version},
        )
        assert response.status_code == 200, response.text
        if action == "deactivate":
            assert (
                await client.post(revisions, headers=command_headers(current), json=payload)
            ).status_code == 409
            assert (
                await client.patch(
                    detail, headers=command_headers(current), json={"expected_version": 1}
                )
            ).status_code == 409
    for invalid in (
        {},
        {"duration": True, "duration_unit": "DAYS"},
        {"duration": "12", "duration_unit": "MONTHS"},
        {"duration": 1201, "duration_unit": "MONTHS"},
        {"duration": 101, "duration_unit": "YEARS"},
        {"duration": 36501, "duration_unit": "DAYS"},
        {"duration": 0, "duration_unit": "DAYS"},
        {**payload, "start_trigger": "ANY"},
        {**payload, "claim_id": str(uuid7())},
        {**payload, "coverage_description": "   "},
        {**payload, "coverage_description": "bad\x00text"},
    ):
        result = await client.post(revisions, headers=command_headers(current), json=invalid)
        assert result.status_code == 422, result.text
    for field in ("duration", "duration_unit", "start_trigger"):
        assert (
            await client.patch(
                detail, headers=command_headers(current), json={"expected_version": 1, field: None}
            )
        ).status_code == 422
    # Validate the merged draft: 1200 DAYS is valid; changing only the unit to YEARS is not.
    update = await client.patch(
        detail,
        headers=command_headers(current),
        json={
            "expected_version": 1,
            "duration": 1200,
            "duration_unit": "DAYS",
            "coverage_description": None,
        },
    )
    assert update.status_code == 200 and update.json()["coverage_description"] is None
    invalid_merge = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 2, "duration_unit": "YEARS"},
    )
    assert invalid_merge.status_code == 422
    noop = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 2, "duration_unit": "DAYS"},
    )
    assert noop.status_code == 200 and noop.json()["row_version"] == 2
    assert (
        await client.patch(detail, headers=command_headers(current), json={"expected_version": 1})
    ).status_code == 409
    publication = command_headers(current)
    result = await client.post(
        detail + "/publish", headers=publication, json={"expected_version": 2}
    )
    assert result.status_code == 200 and result.json()["published_at"]
    assert (
        await client.post(detail + "/publish", headers=publication, json={"expected_version": 2})
    ).headers["Idempotency-Replayed"] == "true"
    assert (
        await client.patch(
            detail, headers=command_headers(current), json={"expected_version": 3, "duration": 1}
        )
    ).status_code == 409
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 3}
        )
    ).status_code == 409
    second = await client.post(
        revisions,
        headers=command_headers(current),
        json={"duration": 2, "duration_unit": "YEARS", "start_trigger": "INSTALLATION"},
    )
    assert second.status_code == 201 and second.json()["revision"] == 2
    page = await client.get(revisions, headers=current, params={"limit": 1, "sort": "-revision"})
    assert page.status_code == 200 and "coverage_description" not in page.json()["items"][0]
    next_page = await client.get(
        revisions,
        headers=current,
        params={"limit": 1, "sort": "-revision", "cursor": page.json()["page"]["next_cursor"]},
    )
    assert next_page.json()["items"][0]["id"] == created.json()["id"]
    for filters in ({"published": "true"}, {"duration_unit": "DAYS", "start_trigger": "SALE"}):
        filtered = await client.get(revisions, headers=current, params=filters)
        assert filtered.status_code == 200 and len(filtered.json()["items"]) == 1
    assert (await client.get(revisions, headers=current, params={"published": "false"})).json()[
        "items"
    ][0]["id"] == second.json()["id"]
    for query in ({"q": "parts"}, {"sort": "duration"}, {"offset": 10}, {"duration_unit": "WEEKS"}):
        assert (await client.get(revisions, headers=current, params=query)).status_code == 422
    assert (
        await client.get(
            route, headers=current, params={"q": "Retail", "is_active": "true", "sort": "name"}
        )
    ).json()["items"][0]["id"] == master.rsplit("/", 1)[-1]
    options = await client.get(
        f"/v1/companies/{company}/option-sources/catalog.warranty_policies", headers=current
    )
    assert options.status_code == 200 and options.json()["items"][0]["code"] == "RETAIL"


async def test_warranty_every_endpoint_requires_auth_and_company_scope(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, user, current, master = await setup_policy(client, factory, tenant_a)
    route, revisions = master.rsplit("/", 1)[0], master + "/revisions"
    payload = {"duration": 24, "duration_unit": "MONTHS", "start_trigger": "DELIVERY"}
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
        ("PATCH", detail, {"expected_version": 1, "duration": 36}),
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


async def test_warranty_field_policy_atomicity_replay_and_read_guards(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, _, master = await setup_policy(client, factory, tenant_a)
    facts = all_facts(company, user)
    source = next(row for row in facts if row.kind == "field_policy")
    policy = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **source.data,
            "entity_type": "catalog.warranty_policy_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "duration",
            "access": "write",
            "condition": {"field": "duration", "cmp": "gt", "value": "30"},
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, policy))
    revisions = master + "/revisions"
    payload = {"duration": 60, "duration_unit": "DAYS"}
    receipt = command_headers(current)
    assert (await client.post(revisions, headers=receipt, json=payload)).status_code == 403
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(WarrantyPolicyRevision.id))) == 0
            assert await db.scalar(select(func.count(IdempotencyKey.id))) == 1
            assert await db.scalar(select(func.count(Outbox.id))) == 1
    payload["duration"] = 30
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
        for key in ("duration_unit", "revision", "published_at", "coverage_description")
    )
    current = await auth(factory, tenant_a, company, user, version=5, facts=(*facts, *hidden))
    page = await client.get(revisions, headers=current)
    assert page.status_code == 200 and "duration_unit" not in page.json()["items"][0]
    assert "coverage_description" not in (await client.get(detail, headers=current)).json()
    for query in ({"duration_unit": "DAYS"}, {"sort": "revision"}, {"published": "true"}):
        assert (await client.get(revisions, headers=current, params=query)).status_code == 403
    metadata = await client.get(
        f"/v1/companies/{company}/entities/catalog.warranty_policy_revision/field-set",
        headers=current,
    )
    assert metadata.status_code == 200
    fields = {entry["key"]: entry for entry in metadata.json()["fields"]}
    assert fields["policy_id"]["writable"] is False and "revision" not in fields
    membership = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={**deny.data, "field_key": "policy_id", "access": "read"},
    )
    current = await auth(factory, tenant_a, company, user, version=6, facts=(*facts, membership))
    for path in (revisions, detail):
        assert (await client.get(path, headers=current)).status_code == 403
