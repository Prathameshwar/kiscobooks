"""Organization form/detail contracts retain object and tenant boundaries."""

from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api_support import actor_headers, grant
from tests.factories import build_user, seed_two_companies

pytestmark = pytest.mark.asyncio


def headers(
    tenant: uuid.UUID, permissions: list[str], company: uuid.UUID | None = None
) -> dict[str, str]:
    return actor_headers(
        tenant_id=tenant,
        user_id=uuid7(),
        grants=[
            grant(
                permissions,
                scope_type="company" if company else "tenant",
                scope_id=company,
            )
        ],
    )


async def test_department_detail_and_metadata_scope(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, other = await seed_two_companies(session, tenant_a, tenant_b)
    h = headers(tenant_a, ["department.read", "department.manage"], company)
    base = f"/v1/companies/{company}/departments"
    created = await client.post(base, headers=h, json={"code": "OPS", "name": "Operations"})
    assert created.status_code == 201, created.text
    did = created.json()["id"]
    detail = await client.get(f"{base}/{did}", headers=h)
    assert detail.status_code == 200, detail.text
    assert detail.json() == created.json()
    metadata = await client.get(f"{base}/field-set?operation=update&id={did}", headers=h)
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["entity_type"] == "identity.department"
    assert {field["key"] for field in metadata.json()["fields"]} == {
        "code",
        "name",
        "cost_centre_code",
        "head_user_id",
    }
    assert (
        await client.get(f"{base}/{did}", headers=headers(tenant_a, ["department.read"], other))
    ).status_code == 403
    assert (
        await client.get(f"{base}/{did}", headers=headers(tenant_b, ["department.read"]))
    ).status_code == 404
    assert (await client.get(f"{base}/{did}")).status_code == 401
    assert (await client.get(f"{base}/field-set?operation=invalid", headers=h)).status_code == 422
    assert (
        await client.get(f"{base}/field-set?operation=create&operation=update", headers=h)
    ).status_code == 422


async def test_department_list_status_filter_and_cursor_binding(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    h = headers(tenant_a, ["department.read", "department.manage"])
    base = f"/v1/companies/{company}/departments"
    for code in ["AA", "AB", "AC"]:
        row = await client.post(base, headers=h, json={"code": code, "name": code})
        assert row.status_code == 201
        if code == "AC":
            assert (
                await client.post(
                    f"{base}/{row.json()['id']}/lifecycle",
                    headers=h,
                    json={"is_active": False, "reason": "Retired"},
                )
            ).status_code == 200
    first = await client.get(f"{base}?is_active=true&sort=code&limit=1", headers=h)
    assert first.status_code == 200, first.text
    assert first.json()["items"][0]["code"] == "AA"
    cursor = first.json()["page"]["next_cursor"]
    assert cursor
    second = await client.get(f"{base}?is_active=true&sort=code&limit=1&cursor={cursor}", headers=h)
    assert second.json()["items"][0]["code"] == "AB"
    assert (
        await client.get(f"{base}?is_active=false&sort=code&limit=1&cursor={cursor}", headers=h)
    ).status_code == 422
    inactive = await client.get(f"{base}?is_active=false", headers=h)
    assert [r["code"] for r in inactive.json()["items"]] == ["AC"]


async def test_group_detail_metadata_and_member_labels(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    uid = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=uid, email=f"{uid}@example.test"))
        await session.commit()
    h = headers(tenant_a, ["group.read", "group.manage", "user.read"])
    created = await client.post(
        "/v1/user-groups", headers=h, json={"code": "FIN", "name": "Finance"}
    )
    assert created.status_code == 201
    base = "/v1/user-groups/" + created.json()["id"]
    assert (await client.get(base, headers=h)).json() == created.json()
    meta = await client.get("/v1/user-groups/field-set?operation=update", headers=h)
    assert meta.status_code == 200, meta.text
    assert {r["key"] for r in meta.json()["fields"]} == {"name", "description"}
    assert (
        await client.post(base + "/members", headers=h, json={"user_id": str(uid)})
    ).status_code == 201
    members = await client.get(base + "/members", headers=h)
    assert members.status_code == 200
    assert members.json()["items"][0]["display_name"]
    restricted = await client.get(base + "/members", headers=headers(tenant_a, ["group.read"]))
    assert restricted.json()["items"][0]["display_name"] is None
    assert (await client.get(base, headers=headers(tenant_b, ["group.read"]))).status_code == 404
    assert (
        await client.get(base, headers=headers(tenant_a, ["group.read"], uuid7()))
    ).status_code == 403
    assert (await client.get(base)).status_code == 401


async def test_group_directory_filters_and_strict_queries(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    h = headers(tenant_a, ["group.read", "group.manage"])
    for code in ["AB", "AA"]:
        assert (
            await client.post("/v1/user-groups", headers=h, json={"code": code, "name": code})
        ).status_code == 201
    result = await client.get("/v1/user-groups?sort=code&is_active=true&limit=1", headers=h)
    assert result.status_code == 200, result.text
    assert result.json()["items"][0]["code"] == "AA"
    gid = result.json()["items"][0]["id"]
    resolved = await client.get(f"/v1/user-groups?id={gid}", headers=h)
    assert len(resolved.json()["items"]) == 1
    for query in [
        "sort=description",
        "limit=201",
        "is_active=invalid",
        "id=invalid",
        "is_active=true&is_active=false",
    ]:
        assert (await client.get("/v1/user-groups?" + query, headers=h)).status_code == 422


async def test_membership_directory_filters_are_scoped(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, other = await seed_two_companies(session, tenant_a, tenant_b)
    users = [uuid7(), uuid7()]
    with tenant_scope(tenant_a):
        for uid in users:
            session.add(build_user(tenant_id=tenant_a, user_id=uid, email=f"{uid}@example.test"))
        await session.commit()
    h = headers(tenant_a, ["department.read", "department.manage"])
    base = f"/v1/companies/{company}/memberships"
    for uid in users:
        assert (await client.post(base, headers=h, json={"user_id": str(uid)})).status_code == 201
    result = await client.get(base + f"?user_id={users[0]}&is_active=true", headers=h)
    assert result.status_code == 200, result.text
    assert [row["user_id"] for row in result.json()["items"]] == [str(users[0])]
    assert (
        await client.get(base, headers=headers(tenant_a, ["department.read"], other))
    ).status_code == 403
    assert (await client.get(base + "?user_id=invalid", headers=h)).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"code": "  ", "name": "Operations"},
        {"code": "OPS", "name": "Bad\x01name"},
    ],
)
async def test_department_rejects_blank_and_control_values(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    payload: dict[str, str],
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    result = await client.post(
        f"/v1/companies/{company}/departments",
        headers=headers(tenant_a, ["department.manage"]),
        json=payload,
    )
    assert result.status_code == 422, result.text


async def test_inactive_department_rejects_profile_and_parent_changes(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    h = headers(tenant_a, ["department.read", "department.manage"])
    base = f"/v1/companies/{company}/departments"
    created = await client.post(base, headers=h, json={"code": "OPS", "name": "Operations"})
    url = base + "/" + created.json()["id"]
    assert (
        await client.post(
            url + "/lifecycle", headers=h, json={"is_active": False, "reason": "Retired"}
        )
    ).status_code == 200
    assert (await client.patch(url, headers=h, json={"name": "Changed"})).status_code == 409
    assert (
        await client.post(url + "/reparent", headers=h, json={"parent_id": None})
    ).status_code == 409


async def test_organisation_directories_use_lean_projections(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    h = headers(tenant_a, ["department.read", "department.manage", "group.read", "group.manage"])
    departments = f"/v1/companies/{company}/departments"
    created = await client.post(
        departments,
        headers=h,
        json={"code": "OPS", "name": "Operations", "cost_centre_code": "COST"},
    )
    assert created.status_code == 201
    directory = await client.get(departments, headers=h)
    assert "cost_centre_code" not in directory.json()["items"][0]
    assert "head_user_id" not in directory.json()["items"][0]
    group = await client.post(
        "/v1/user-groups",
        headers=h,
        json={"code": "TEAM", "name": "Team", "description": "Detail only"},
    )
    assert group.status_code == 201
    groups = await client.get("/v1/user-groups", headers=h)
    assert "description" not in groups.json()["items"][0]
