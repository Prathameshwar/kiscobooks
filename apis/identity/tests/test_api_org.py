"""HTTP tests for the org structure and department-scoped assignment."""

from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api_support import actor_headers, grant
from tests.factories import build_user, seed_system_role, seed_two_companies

pytestmark = pytest.mark.asyncio


def _h(
    tenant_id: uuid.UUID,
    perms: list[str],
    user_id: uuid.UUID | None = None,
    scope_type: str = "tenant",
    scope_id: uuid.UUID | None = None,
) -> dict[str, str]:
    return actor_headers(
        tenant_id=tenant_id,
        user_id=user_id or uuid7(),
        grants=[grant(perms, scope_type=scope_type, scope_id=scope_id)],
    )


async def _seed_user(session: AsyncSession, tenant_id: uuid.UUID, uid: uuid.UUID) -> None:
    with tenant_scope(tenant_id):
        session.add(build_user(tenant_id=tenant_id, user_id=uid, email=f"{uid}@alpha.example"))
        await session.commit()


# --- departments --------------------------------------------------------------


async def test_create_and_nest_departments(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _h(tenant_a, ["department.manage", "department.read"])
    root = await client.post(
        f"/v1/companies/{company_a}/departments",
        json={"code": "OPS", "name": "Operations"},
        headers=headers,
    )
    assert root.status_code == 201, root.text
    root_id = root.json()["id"]
    assert root.json()["path"] == f"/{uuid.UUID(root_id).hex}/"

    child = await client.post(
        f"/v1/companies/{company_a}/departments",
        json={"code": "OPS-IN", "name": "Ops India", "parent_id": root_id},
        headers=headers,
    )
    assert child.status_code == 201
    assert child.json()["path"].startswith(f"/{uuid.UUID(root_id).hex}/")


async def test_reparent_rewrites_subtree_paths(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _h(tenant_a, ["department.manage", "department.read"])

    async def mk(code: str, parent: str | None = None) -> str:
        resp = await client.post(
            f"/v1/companies/{company_a}/departments",
            json={"code": code, "name": code, "parent_id": parent},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return str(resp.json()["id"])

    a = await mk("A")
    b = await mk("B")
    child = await mk("A-CHILD", parent=a)  # under A

    # Move A under B; A and its child must now sit beneath B.
    moved = await client.post(
        f"/v1/companies/{company_a}/departments/{a}/reparent",
        json={"parent_id": b},
        headers=headers,
    )
    assert moved.status_code == 200
    assert moved.json()["path"].startswith(f"/{uuid.UUID(b).hex}/{uuid.UUID(a).hex}/")

    listing = await client.get(f"/v1/companies/{company_a}/departments", headers=headers)
    paths = {i["id"]: i["path"] for i in listing.json()["items"]}
    assert paths[child].startswith(f"/{uuid.UUID(b).hex}/{uuid.UUID(a).hex}/")


async def test_reparent_cycle_is_409(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = _h(tenant_a, ["department.manage", "department.read"])
    a = (
        await client.post(
            f"/v1/companies/{company_a}/departments",
            json={"code": "A", "name": "A"},
            headers=headers,
        )
    ).json()["id"]
    child = (
        await client.post(
            f"/v1/companies/{company_a}/departments",
            json={"code": "C", "name": "C", "parent_id": a},
            headers=headers,
        )
    ).json()["id"]
    # Move A under its own descendant → cycle.
    resp = await client.post(
        f"/v1/companies/{company_a}/departments/{a}/reparent",
        json={"parent_id": child},
        headers=headers,
    )
    assert resp.status_code == 409


async def test_department_without_permission_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    resp = await client.post(
        f"/v1/companies/{company_a}/departments",
        json={"code": "X", "name": "X"},
        headers=_h(tenant_a, ["department.read"]),
    )
    assert resp.status_code == 403


# --- groups & membership ------------------------------------------------------


async def test_group_create_and_add_member(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    uid = uuid7()
    await _seed_user(session, tenant_a, uid)
    headers = _h(tenant_a, ["group.manage", "group.read"])
    group = await client.post(
        "/v1/user-groups", json={"code": "finance", "name": "Finance"}, headers=headers
    )
    assert group.status_code == 201
    gid = group.json()["id"]
    added = await client.post(
        f"/v1/user-groups/{gid}/members", json={"user_id": str(uid)}, headers=headers
    )
    assert added.status_code == 201
    members = await client.get(f"/v1/user-groups/{gid}/members", headers=headers)
    assert {m["user_id"] for m in members.json()["items"]} == {str(uid)}


async def test_membership_create(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    uid = uuid7()
    await _seed_user(session, tenant_a, uid)
    headers = _h(tenant_a, ["department.manage", "department.read"])
    resp = await client.post(
        f"/v1/companies/{company_a}/memberships",
        json={"user_id": str(uid), "is_primary": True},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["company_id"] == str(company_a)


async def test_duplicate_membership_is_409_not_500(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A unique-constraint collision that no route pre-checks surfaces as a clean 409
    envelope, never a raw 500 with driver SQL (CLAUDE.md §5.8). Uses a membership at a
    named department, where ``(user, company, department)`` is genuinely unique — a
    company-level membership (NULL department) is distinct-in-unique and can repeat
    (db-plan §2 NULL trap; see the review finding)."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    uid = uuid7()
    await _seed_user(session, tenant_a, uid)
    headers = _h(tenant_a, ["department.manage", "department.read"])
    dept = await client.post(
        f"/v1/companies/{company_a}/departments",
        json={"code": "OPS", "name": "Operations"},
        headers=headers,
    )
    dept_id = dept.json()["id"]
    body = {"user_id": str(uid), "department_id": dept_id, "is_primary": True}
    first = await client.post(f"/v1/companies/{company_a}/memberships", json=body, headers=headers)
    assert first.status_code == 201
    dup = await client.post(f"/v1/companies/{company_a}/memberships", json=body, headers=headers)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "conflict"


# --- department-scoped assignment (Phase 6 unblocks this) ---------------------


async def test_assign_role_at_department_scope(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    role_id = await seed_system_role(session, key="viewer", permission_key="invoice.read")
    subject = uuid7()
    await _seed_user(session, tenant_a, subject)

    dept = await client.post(
        f"/v1/companies/{company_a}/departments",
        json={"code": "SALES", "name": "Sales"},
        headers=_h(tenant_a, ["department.manage"]),
    )
    dept_id = dept.json()["id"]

    # Actor holds role.assign + invoice.read at COMPANY scope — a company grant reaches
    # a department within it, so the department-scope assignment is permitted (guard 3).
    headers = _h(
        tenant_a, ["role.assign", "invoice.read"], scope_type="company", scope_id=company_a
    )
    resp = await client.post(
        "/v1/role-assignments",
        json={
            "subject_type": "user",
            "subject_id": str(subject),
            "role_id": str(role_id),
            "scope_type": "department",
            "scope_id": dept_id,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["scope_id"] == dept_id
