import uuid
from typing import Any

import httpx
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.profile_factories import auth
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_commercial_api import command_headers

REQUIREMENTS = [
    {
        "identifier_type": "SERIAL",
        "namespace_rule": "MANUFACTURER_SKU",
        "min_count": 1,
        "max_count": 1,
    },
    {
        "identifier_type": "IMEI",
        "namespace_rule": "COMPANY",
        "min_count": 2,
        "max_count": 2,
        "requires_slot": True,
    },
]


async def test_missing_immutable_requirements_cannot_replay_success(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from billing_platform.db import tenant_scope
    from sqlalchemy import select

    from catalog.models.profiles import IdentifierProfileRequirement

    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/identifier-profiles"
    body = {"code": "DEVICE", "name": "Device", "requirements": REQUIREMENTS}
    receipt = command_headers(current)
    assert (await client.post(route, headers=receipt, json=body)).status_code == 201
    # Simulate inconsistent restored data; the API itself never removes requirements.
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            for row in await db.scalars(select(IdentifierProfileRequirement)):
                await db.delete(row)
    assert (await client.post(route, headers=receipt, json=body)).status_code == 409


async def test_identifier_profile_crud_and_immutable_requirements(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/identifier-profiles"
    body = {"code": "PHONE", "name": "Phone", "requirements": REQUIREMENTS}
    assert (await client.post(route, json=body)).status_code == 401
    reader = headers(company, tenant=tenant_a, user=user, permission="identifier_profile.read")
    assert (await client.post(route, headers=command_headers(reader), json=body)).status_code == 403
    receipt = command_headers(current)
    created = await client.post(route, headers=receipt, json=body)
    assert created.status_code == 201, created.text
    assert created.json()["normalization_version"] == 1
    assert "requirements" not in created.json()
    assert (await client.post(route, headers=receipt, json=body)).headers[
        "Idempotency-Replayed"
    ] == "true"
    assert (
        await client.post(route, headers=command_headers(current), json=body)
    ).status_code == 409
    changes: dict[str, Any]
    for changes in (
        {"requirements": []},
        {"requirements": [REQUIREMENTS[0], REQUIREMENTS[0]]},
        {"normalization_version": 2},
        {"imei_values": ["physical-device-value"]},
    ):
        assert (
            await client.post(route, headers=command_headers(current), json={**body, **changes})
        ).status_code == 422
    detail = route + "/" + created.json()["id"]
    assert (await client.get(detail, headers=current)).status_code == 200
    first = await client.get(
        detail + "/requirements", headers=current, params={"limit": 1, "sort": "identifier_type"}
    )
    assert (
        first.status_code == 200 and first.json()["items"][0]["identifier_type"] == "IMEI"
    ), first.text
    following = await client.get(
        detail + "/requirements",
        headers=current,
        params={
            "limit": 1,
            "sort": "identifier_type",
            "cursor": first.json()["page"]["next_cursor"],
        },
    )
    assert following.json()["items"][0]["identifier_type"] == "SERIAL"
    assert (
        await client.get(
            detail + "/requirements", headers=current, params={"identifier_type": "IMEI"}
        )
    ).json()["items"][0]["min_count"] == 2
    assert (
        await client.get(detail + "/requirements", headers=current, params={"q": "IMEI"})
    ).status_code == 422
    assert (await client.get(route, headers=current, params={"q": "Ph", "sort": "-name"})).json()[
        "items"
    ][0]["id"] == created.json()["id"]
    assert (
        await client.patch(
            detail, headers=command_headers(current), json={"expected_version": 1, "code": "OTHER"}
        )
    ).status_code == 409
    assert (
        await client.patch(
            detail,
            headers=command_headers(current),
            json={"expected_version": 1, "requirements": REQUIREMENTS},
        )
    ).status_code == 422
    updated = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 1, "name": "Mobile phone"},
    )
    assert updated.status_code == 200 and updated.json()["row_version"] == 2, updated.text
    assert (
        await client.patch(
            detail, headers=command_headers(current), json={"expected_version": 1, "name": "Stale"}
        )
    ).status_code == 409
    for action, version in (("deactivate", 2), ("activate", 3)):
        assert (
            await client.post(
                detail + "/" + action,
                headers=command_headers(current),
                json={"expected_version": version},
            )
        ).status_code == 200
    other_company = uuid7()
    other = await auth(factory, tenant_a, other_company, user)
    for suffix in ("", "/requirements"):
        assert (
            await client.get(
                detail.replace(str(company), str(other_company)) + suffix, headers=other
            )
        ).status_code == 403
    alien = await auth(factory, tenant_b, company, user)
    assert (await client.get(detail, headers=alien)).status_code == 404
    options = await client.get(
        f"/v1/companies/{company}/option-sources/catalog.identifier_profiles", headers=current
    )
    assert (
        options.status_code == 200 and options.json()["items"][0]["value"] == created.json()["id"]
    ), options.text


async def test_requirement_policy_protects_creation_replay_and_reads(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    current = await auth(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/identifier-profiles"
    body = {"code": "PHONE", "name": "Phone", "requirements": REQUIREMENTS}
    receipt = command_headers(current)
    first = await client.post(route, headers=receipt, json=body)
    assert first.status_code == 201, first.text
    policy = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.identifier_profile_requirement",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "max_count",
            "access": "write",
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, deny))
    assert (await client.post(route, headers=receipt, json=body)).status_code == 403
    assert (
        await client.post(route, headers=command_headers(current), json={**body, "code": "BLOCKED"})
    ).status_code == 403
    assert len((await client.get(route, headers=current)).json()["items"]) == 1
    hidden = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={**deny.data, "field_key": "profile_id", "access": "read"},
    )
    current = await auth(factory, tenant_a, company, user, version=4, facts=(*facts, hidden))
    assert (
        await client.get(route + "/" + first.json()["id"] + "/requirements", headers=current)
    ).status_code == 403


async def test_conditional_requirement_policy_rolls_back_the_whole_profile(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from billing_platform.db import tenant_scope
    from sqlalchemy import func, select

    from catalog.models import IdempotencyKey, Outbox
    from catalog.models.profiles import IdentifierProfile, IdentifierProfileRequirement

    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    policy = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.identifier_profile_requirement",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "max_count",
            "access": "write",
            "condition": {"field": "max_count", "cmp": "gt", "value": "1"},
        },
    )
    current = await auth(factory, tenant_a, company, user, facts=(*facts, deny))
    route = f"/v1/companies/{company}/identifier-profiles"
    receipt = command_headers(current)
    body = {"code": "DEVICE", "name": "Device", "requirements": REQUIREMENTS}
    assert (await client.post(route, headers=receipt, json=body)).status_code == 403
    with tenant_scope(tenant_a):
        async with factory() as db:
            for model in (IdentifierProfile, IdentifierProfileRequirement, IdempotencyKey, Outbox):
                assert await db.scalar(select(func.count(model.id))) == 0
    # A rejected command left no receipt: retry with a valid requirement and the same key.
    allowed = await client.post(
        route, headers=receipt, json={**body, "requirements": [REQUIREMENTS[0]]}
    )
    assert allowed.status_code == 201, allowed.text
    assert (
        await client.post(route, headers=receipt, json={**body, "requirements": [REQUIREMENTS[0]]})
    ).status_code == 201
    with tenant_scope(tenant_a):
        async with factory() as db:
            event = await db.scalar(select(Outbox))
            assert event is not None and event.event_type == "catalog.identifier_profile.create"
            assert event.payload["company_id"] == str(company)
            assert "requirements" in event.payload["changes"]
    for entity, field in (
        ("identifier_profile", "normalization_version"),
        ("identifier_profile_requirement", "profile_id"),
    ):
        response = await client.get(
            f"/v1/companies/{company}/entities/catalog.{entity}/field-set", headers=current
        )
        assert response.status_code == 200, response.text
        fields = {entry["key"]: entry for entry in response.json()["fields"]}
        assert not fields[field]["writable"]
    revoked = SnapshotRecord(
        kind="field_policy",
        id=deny.id,
        data={
            **deny.data,
            "condition": {"field": "max_count", "cmp": "gte", "value": "1"},
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, revoked))
    assert (
        await client.post(
            route,
            headers={**receipt, **current},
            json={**body, "requirements": [REQUIREMENTS[0]]},
        )
    ).status_code == 403
