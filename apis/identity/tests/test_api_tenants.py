"""HTTP tests for tenant self-service."""

from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api_support import actor_headers, grant
from tests.factories import seed_two_tenants

pytestmark = pytest.mark.asyncio


def _headers(tenant_id: uuid.UUID, perms: list[str]) -> dict[str, str]:
    return actor_headers(tenant_id=tenant_id, user_id=uuid7(), grants=[grant(perms)])


async def test_get_tenant_returns_own(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.get("/v1/tenant", headers=_headers(tenant_a, ["tenant.read"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(tenant_a)
    assert body["slug"] == "alpha"


async def test_get_tenant_isolation(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The actor of tenant B gets tenant B — never tenant A's row."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.get("/v1/tenant", headers=_headers(tenant_b, ["tenant.read"]))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(tenant_b)


async def test_get_tenant_unauthenticated_401(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.get("/v1/tenant")
    assert resp.status_code == 401


async def test_update_tenant_happy(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.patch(
        "/v1/tenant",
        json={"name": "Alpha Renamed", "primary_contact_email": "Ops@Alpha.example"},
        headers=_headers(tenant_a, ["tenant.update"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Alpha Renamed"
    assert body["primary_contact_email"] == "ops@alpha.example"


async def test_update_tenant_without_permission_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.patch(
        "/v1/tenant", json={"name": "X"}, headers=_headers(tenant_a, ["tenant.read"])
    )
    assert resp.status_code == 403


async def test_update_tenant_unknown_field_422(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    resp = await client.patch(
        "/v1/tenant",
        json={"slug": "hijack"},  # slug is immutable and not an accepted field
        headers=_headers(tenant_a, ["tenant.update"]),
    )
    assert resp.status_code == 422
