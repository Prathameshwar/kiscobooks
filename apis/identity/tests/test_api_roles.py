"""HTTP-level tests for roles and role assignments — the authorization surface.

The centrepiece is the three escalation guards (docs/roles-permissions.md §1.5): you
cannot compose or assign a permission you do not hold, cannot assign at a scope broader
than your own, and cannot change your own assignments. A system role is read-only (422).
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api_support import actor_headers, grant
from tests.factories import build_user, seed_system_role, seed_two_tenants

pytestmark = pytest.mark.asyncio


async def _seed_user(session: AsyncSession, tenant_id: uuid.UUID, uid: uuid.UUID) -> None:
    with tenant_scope(tenant_id):
        session.add(build_user(tenant_id=tenant_id, user_id=uid, email=f"{uid}@alpha.example"))
        await session.commit()


# --- role composition ---------------------------------------------------------


async def test_create_role_happy(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["role.manage", "invoice.read", "invoice.create"])],
    )
    resp = await client.post(
        "/v1/roles",
        json={"key": "junior_biller", "name": "Junior Biller", "permissions": ["invoice.read"]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"]["key"] == "junior_biller"
    assert body["role"]["is_system"] is False
    assert body["role"]["permissions"] == ["invoice.read"]


async def test_create_role_with_unheld_permission_is_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Guard 1: a role cannot grant what its composer does not hold."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["role.manage", "invoice.read"])]
    )
    resp = await client.post(
        "/v1/roles",
        json={"key": "over_reach", "name": "Over Reach", "permissions": ["period.lock"]},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_create_role_without_manage_is_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["invoice.read"])])
    resp = await client.post(
        "/v1/roles",
        json={"key": "nope", "name": "Nope", "permissions": ["invoice.read"]},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_create_role_unknown_permission_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["role.manage"])])
    resp = await client.post(
        "/v1/roles",
        json={"key": "typo", "name": "Typo", "permissions": ["invoice.reed"]},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_create_role_reports_separation_of_duties_warning(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A tenant may combine a segregated pair, but the pair is surfaced (not rejected)."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["role.manage", "role.assign", "audit.read_security"])],
    )
    resp = await client.post(
        "/v1/roles",
        json={
            "key": "risky_bundle",
            "name": "Risky Bundle",
            "permissions": ["role.assign", "audit.read_security"],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["separation_of_duties_warnings"]


async def test_edit_system_role_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    role_id = await seed_system_role(session, key="viewer", permission_key="invoice.read")
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["role.manage"])])
    resp = await client.patch(f"/v1/roles/{role_id}", json={"name": "Hijacked"}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "immutable_field"


async def test_clone_system_role_creates_tenant_copy(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    role_id = await seed_system_role(session, key="viewer", permission_key="invoice.read")
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["role.manage", "invoice.read"])]
    )
    resp = await client.post(
        f"/v1/roles/{role_id}/clone", json={"key": "my_viewer"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_system"] is False
    assert body["cloned_from_role_id"] == str(role_id)
    assert body["permissions"] == ["invoice.read"]


# --- assignment guards --------------------------------------------------------


async def test_assign_role_happy(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    role_id = await seed_system_role(session, key="viewer", permission_key="invoice.read")
    subject = uuid7()
    await _seed_user(session, tenant_a, subject)
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["role.assign", "invoice.read"])]
    )
    resp = await client.post(
        "/v1/role-assignments",
        json={
            "subject_type": "user",
            "subject_id": str(subject),
            "role_id": str(role_id),
            "scope_type": "tenant",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["scope_id"] is None  # SCOPE_ALL never crosses the boundary


async def test_assign_role_you_do_not_hold_is_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Guard 1 on assignment: cannot hand out a permission you lack."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    role_id = await seed_system_role(session, key="closer", permission_key="period.close")
    subject = uuid7()
    await _seed_user(session, tenant_a, subject)
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["role.assign", "invoice.read"])]
    )
    resp = await client.post(
        "/v1/role-assignments",
        json={
            "subject_type": "user",
            "subject_id": str(subject),
            "role_id": str(role_id),
            "scope_type": "tenant",
        },
        headers=headers,
    )
    assert resp.status_code == 403


async def test_cannot_assign_to_self(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Guard 2: you cannot change your own assignments."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    role_id = await seed_system_role(session, key="viewer", permission_key="invoice.read")
    me = uuid7()
    await _seed_user(session, tenant_a, me)
    headers = actor_headers(
        tenant_id=tenant_a, user_id=me, grants=[grant(["role.assign", "invoice.read"])]
    )
    resp = await client.post(
        "/v1/role-assignments",
        json={
            "subject_type": "user",
            "subject_id": str(me),
            "role_id": str(role_id),
            "scope_type": "tenant",
        },
        headers=headers,
    )
    assert resp.status_code == 403


async def test_cannot_assign_broader_than_own_scope(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Guard 3: a company-scoped granter cannot make a tenant-wide assignment."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    role_id = await seed_system_role(session, key="viewer", permission_key="invoice.read")
    subject = uuid7()
    await _seed_user(session, tenant_a, subject)
    company = uuid7()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["role.assign", "invoice.read"], scope_type="company", scope_id=company)],
    )
    resp = await client.post(
        "/v1/role-assignments",
        json={
            "subject_type": "user",
            "subject_id": str(subject),
            "role_id": str(role_id),
            "scope_type": "tenant",
        },
        headers=headers,
    )
    assert resp.status_code == 403


async def test_assign_at_company_scope_happy(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    from tests.factories import seed_two_companies

    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    role_id = await seed_system_role(session, key="viewer", permission_key="invoice.read")
    subject = uuid7()
    await _seed_user(session, tenant_a, subject)
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["role.assign", "invoice.read"], scope_type="company", scope_id=company)],
    )
    resp = await client.post(
        "/v1/role-assignments",
        json={
            "subject_type": "user",
            "subject_id": str(subject),
            "role_id": str(role_id),
            "scope_type": "company",
            "scope_id": str(company),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["scope_id"] == str(company)


async def test_revoke_assignment(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    role_id = await seed_system_role(session, key="viewer", permission_key="invoice.read")
    subject = uuid7()
    await _seed_user(session, tenant_a, subject)
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["role.assign", "invoice.read"])]
    )
    created = await client.post(
        "/v1/role-assignments",
        json={
            "subject_type": "user",
            "subject_id": str(subject),
            "role_id": str(role_id),
            "scope_type": "tenant",
        },
        headers=headers,
    )
    assignment_id = created.json()["id"]
    resp = await client.post(f"/v1/role-assignments/{assignment_id}/revoke", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# --- catalogue & auth ---------------------------------------------------------


async def test_permission_catalogue(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["role.read"])])
    resp = await client.get("/v1/permissions", headers=headers)
    assert resp.status_code == 200
    perms = resp.json()["permissions"]
    assert "company.read" in perms and "invoice.post" in perms


async def test_roles_unauthenticated_is_401(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.get("/v1/roles")
    assert resp.status_code == 401
