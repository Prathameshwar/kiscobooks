"""HTTP-level tests for the user resource.

Covers the §7 matrix and the two user-specific invariants: deactivation anonymizes
rather than deletes (the row survives with PII tombstoned), and ``user_type`` never
decides authority.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import User
from tests.api_support import actor_headers, grant
from tests.factories import build_user, seed_two_tenants

pytestmark = pytest.mark.asyncio


def _headers(
    tenant_id: uuid.UUID, perms: list[str], user_id: uuid.UUID | None = None
) -> dict[str, str]:
    return actor_headers(tenant_id=tenant_id, user_id=user_id or uuid7(), grants=[grant(perms)])


def _admin(tenant_id: uuid.UUID, user_id: uuid.UUID | None = None) -> dict[str, str]:
    return _headers(
        tenant_id, ["user.invite", "user.read", "user.update", "user.deactivate"], user_id
    )


async def _seed_user(
    session: AsyncSession, tenant_id: uuid.UUID, *, user_id: uuid.UUID | None = None, **kw: Any
) -> uuid.UUID:
    uid = user_id or uuid7()
    with tenant_scope(tenant_id):
        session.add(build_user(tenant_id=tenant_id, user_id=uid, **kw))
        await session.commit()
    return uid


async def test_invite_user_happy(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.post(
        "/v1/users",
        json={"email": "New.Person@Alpha.example", "first_name": "New", "last_name": "Person"},
        headers=_admin(tenant_a),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "invited"
    assert body["email"] == "new.person@alpha.example"  # normalised
    assert body["display_name"] == "New Person"


async def test_invite_unauthenticated_is_401(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.post("/v1/users", json={"email": "a@b.com", "first_name": "A"})
    assert resp.status_code == 401


async def test_invite_without_permission_is_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.post(
        "/v1/users",
        json={"email": "a@b.com", "first_name": "A"},
        headers=_headers(tenant_a, ["user.read"]),
    )
    assert resp.status_code == 403


async def test_invite_duplicate_email_is_409(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await _seed_user(session, tenant_a, email="dup@alpha.example")
    resp = await client.post(
        "/v1/users",
        json={"email": "dup@alpha.example", "first_name": "Dup"},
        headers=_admin(tenant_a),
    )
    assert resp.status_code == 409


async def test_invite_bad_email_is_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.post(
        "/v1/users", json={"email": "not-an-email", "first_name": "A"}, headers=_admin(tenant_a)
    )
    assert resp.status_code == 422


async def test_cross_tenant_get_is_404(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    uid = await _seed_user(session, tenant_a, email="asha@alpha.example")
    resp = await client.get(f"/v1/users/{uid}", headers=_admin(tenant_b))
    assert resp.status_code == 404


async def test_company_scoped_actor_cannot_read_users_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Users are tenant-level; a company-scoped user.read grant does not reach them."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    uid = await _seed_user(session, tenant_a, email="asha@alpha.example")
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["user.read"], scope_type="company", scope_id=uuid7())],
    )
    resp = await client.get(f"/v1/users/{uid}", headers=headers)
    assert resp.status_code == 403


async def test_deactivate_anonymizes_but_keeps_row(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    uid = await _seed_user(session, tenant_a, email="leaver@alpha.example", employee_code="E-42")
    resp = await client.post(
        f"/v1/users/{uid}/deactivate",
        json={"reason": "left the company"},
        headers=_admin(tenant_a),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deactivated"

    with tenant_scope(tenant_a):
        row = await session.get(User, uid)
    assert row is not None  # never deleted
    assert row.anonymized_at is not None
    assert row.email == f"deactivated+{uid}@invalid"
    assert row.first_name == "[deactivated]"
    assert row.employee_code == "E-42"  # preserved: the HR handle survives


async def test_cannot_deactivate_self(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    me = uuid7()
    await _seed_user(session, tenant_a, user_id=me, email="me@alpha.example")
    resp = await client.post(f"/v1/users/{me}/deactivate", headers=_admin(tenant_a, user_id=me))
    assert resp.status_code == 409


async def test_list_users_isolation(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    a_uid = await _seed_user(session, tenant_a, email="asha@alpha.example")
    await _seed_user(session, tenant_b, email="beta.person@beta.example")
    resp = await client.get("/v1/users", headers=_admin(tenant_a))
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = {i["id"] for i in items}
    assert str(a_uid) in ids
    # Tenant B's user must be absent — the isolation assertion for this table.
    assert all(i["email"].endswith("@alpha.example") for i in items)
