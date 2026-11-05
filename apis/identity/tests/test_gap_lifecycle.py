from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import User
from tests.api_support import actor_headers, grant
from tests.factories import build_user, seed_two_companies

pytestmark = pytest.mark.asyncio
PERMS = [
    "company.read",
    "company.deactivate",
    "department.manage",
    "department.read",
    "group.manage",
    "group.read",
    "role.manage",
    "role.assign",
    "user.read",
    "user.deactivate",
]


async def test_company_closure_is_terminal_and_history_readable(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, other = await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(PERMS)])
    url = f"/v1/companies/{company}/lifecycle"
    assert (
        await client.post(url, headers=headers, json={"status": "closed", "reason": "retired"})
    ).status_code == 200
    assert (
        await client.post(url, headers=headers, json={"status": "closed", "reason": "repeat"})
    ).status_code == 200
    assert (
        await client.post(url, headers=headers, json={"status": "active", "reason": "restore"})
    ).status_code == 409
    assert (await client.get(f"/v1/companies/{company}", headers=headers)).status_code == 200
    assert (
        await client.post(
            f"/v1/companies/{company}/departments",
            headers=headers,
            json={"code": "NEW", "name": "New"},
        )
    ).status_code == 409
    assert (
        await client.post(
            f"/v1/companies/{other}/lifecycle",
            headers=headers,
            json={"status": "closed", "reason": "retired"},
        )
    ).status_code == 404
    limited = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(PERMS, scope_type="company", scope_id=other)],
    )
    assert (
        await client.post(url, headers=limited, json={"status": "closed", "reason": "repeat"})
    ).status_code == 403
    assert (
        await client.post(url, json={"status": "closed", "reason": "repeat"})
    ).status_code == 401


async def test_primary_switch_and_end_preserve_affiliation_history(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    uid = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=uid))
        await session.commit()
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(PERMS)])
    dep = await client.post(
        f"/v1/companies/{company}/departments", headers=headers, json={"code": "OPS", "name": "Ops"}
    )
    assert dep.status_code == 201
    a = await client.post(
        f"/v1/companies/{company}/memberships",
        headers=headers,
        json={"user_id": str(uid), "is_primary": True},
    )
    b = await client.post(
        f"/v1/companies/{company}/memberships",
        headers=headers,
        json={"user_id": str(uid), "department_id": dep.json()["id"]},
    )
    assert a.status_code == b.status_code == 201
    url = f"/v1/memberships/{b.json()['id']}"
    for _ in range(2):
        result = await client.post(
            url + "/make-primary", headers=headers, json={"reason": "transfer"}
        )
        assert result.status_code == 200, result.text
    rows = (await client.get(f"/v1/companies/{company}/memberships", headers=headers)).json()[
        "items"
    ]
    assert sum(row["is_primary"] for row in rows) == 1
    for _ in range(2):
        assert (
            await client.post(url + "/end", headers=headers, json={"reason": "left"})
        ).status_code == 200
    assert (
        await client.post(url + "/make-primary", headers=headers, json={"reason": "retry"})
    ).status_code == 409
    with tenant_scope(tenant_a):
        user = await session.scalar(
            select(User).where(User.id == uid).execution_options(populate_existing=True)
        )
        assert user is not None and user.default_company_id is None


async def test_group_lifecycle_member_removal_and_self_guard(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    uid, admin = uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add_all(
            [
                build_user(tenant_id=tenant_a, user_id=uid),
                build_user(tenant_id=tenant_a, user_id=admin, email="admin@test.example"),
            ]
        )
        await session.commit()
    headers = actor_headers(tenant_id=tenant_a, user_id=admin, grants=[grant(PERMS)])
    group = await client.post(
        "/v1/user-groups", headers=headers, json={"code": "OPS", "name": "Ops"}
    )
    gid = group.json()["id"]
    assert (
        await client.patch(f"/v1/user-groups/{gid}", headers=headers, json={"name": "Operations"})
    ).status_code == 200
    assert (
        await client.post(
            f"/v1/user-groups/{gid}/members", headers=headers, json={"user_id": str(uid)}
        )
    ).status_code == 201
    for _ in range(2):
        assert (
            await client.delete(f"/v1/user-groups/{gid}/members/{uid}", headers=headers)
        ).status_code == 204
    for enabled in [False, True]:
        result = await client.post(
            f"/v1/user-groups/{gid}/lifecycle",
            headers=headers,
            json={"is_active": enabled, "reason": "maintenance"},
        )
        assert result.status_code == 200, result.text
    assert (
        await client.post(
            f"/v1/user-groups/{gid}/members", headers=headers, json={"user_id": str(admin)}
        )
    ).status_code == 201
    assert (
        await client.post(
            f"/v1/user-groups/{gid}/lifecycle",
            headers=headers,
            json={"is_active": False, "reason": "maintenance"},
        )
    ).status_code == 403
    assert (
        await client.delete(f"/v1/user-groups/{gid}/members/{admin}", headers=headers)
    ).status_code == 403


async def test_group_assignment_and_role_lifecycle_are_guarded(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(PERMS)])
    group = (
        await client.post(
            "/v1/user-groups", headers=headers, json={"code": "READERS", "name": "Readers"}
        )
    ).json()
    role = await client.post(
        "/v1/roles",
        headers=headers,
        json={"key": "readers", "name": "Readers", "permissions": ["user.read"]},
    )
    assert role.status_code == 201, role.text
    rid = role.json()["role"]["id"]
    assigned = await client.post(
        "/v1/role-assignments",
        headers=headers,
        json={
            "subject_type": "user_group",
            "subject_id": group["id"],
            "role_id": rid,
            "scope_type": "tenant",
        },
    )
    assert assigned.status_code == 201, assigned.text
    limited = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["role.manage", "role.assign"])]
    )
    assert (
        await client.post(
            f"/v1/roles/{rid}/lifecycle",
            headers=limited,
            json={"is_active": False, "reason": "remove"},
        )
    ).status_code == 403
    for enabled in [False, True]:
        result = await client.post(
            f"/v1/roles/{rid}/lifecycle",
            headers=headers,
            json={"is_active": enabled, "reason": "maintenance"},
        )
        assert result.status_code == 200, result.text


async def test_department_parent_and_user_lifecycle(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    uid = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=uid))
        await session.commit()
    admin = uuid7()
    headers = actor_headers(tenant_id=tenant_a, user_id=admin, grants=[grant(PERMS)])
    parent = (
        await client.post(
            f"/v1/companies/{company}/departments",
            headers=headers,
            json={"code": "P", "name": "Parent"},
        )
    ).json()["id"]
    child = (
        await client.post(
            f"/v1/companies/{company}/departments",
            headers=headers,
            json={"code": "C", "name": "Child", "parent_id": parent},
        )
    ).json()["id"]
    body = {"is_active": False, "reason": "retire"}
    url = f"/v1/companies/{company}/departments"
    assert (
        await client.post(f"{url}/{parent}/lifecycle", headers=headers, json=body)
    ).status_code == 409
    for dep in [child, parent]:
        assert (
            await client.post(f"{url}/{dep}/lifecycle", headers=headers, json=body)
        ).status_code == 200
    assert (
        await client.post(
            f"{url}/{child}/lifecycle", headers=headers, json={**body, "is_active": True}
        )
    ).status_code == 409
    for state in ["suspended", "active"]:
        assert (
            await client.post(
                f"/v1/users/{uid}/lifecycle",
                headers=headers,
                json={"status": state, "reason": "maintenance"},
            )
        ).status_code == 200
    assert (
        await client.post(
            f"/v1/users/{admin}/lifecycle",
            headers=headers,
            json={"status": "suspended", "reason": "maintenance"},
        )
    ).status_code == 403
