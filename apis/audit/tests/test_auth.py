"""The signed actor-context boundary (docs/audit.md §5.1; CLAUDE.md §5.4, §5.8)."""

from __future__ import annotations

import time
import uuid

import httpx
import pytest

from tests.api_support import actor_headers, grant

pytestmark = pytest.mark.asyncio


async def test_tampered_signature_is_401(client: httpx.AsyncClient, tenant_a: uuid.UUID) -> None:
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid.uuid4(), grants=[grant(["audit.read"])]
    )
    headers["X-Actor-Signature"] = "deadbeef"  # not the HMAC of the body
    resp = await client.get("/v1/audit-events", headers=headers)
    assert resp.status_code == 401


async def test_stale_context_is_401(client: httpx.AsyncClient, tenant_a: uuid.UUID) -> None:
    # Issued well outside the acceptance window — a replayed stale header is useless.
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid.uuid4(),
        grants=[grant(["audit.read"])],
        issued_at=int(time.time()) - 3600,
    )
    resp = await client.get("/v1/audit-events", headers=headers)
    assert resp.status_code == 401


async def test_wrong_signing_key_is_401(client: httpx.AsyncClient, tenant_a: uuid.UUID) -> None:
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid.uuid4(),
        grants=[grant(["audit.read"])],
        secret="a-different-key-the-app-does-not-hold",
    )
    resp = await client.get("/v1/audit-events", headers=headers)
    assert resp.status_code == 401


async def test_time_bounded_grant_is_honoured(
    client: httpx.AsyncClient, tenant_a: uuid.UUID
) -> None:
    # A grant whose window has closed does not authorize, at the endpoint gate and the
    # object-level check alike (Actor.permissions honours valid_from/valid_to, not just
    # is_active).
    expired = grant(["audit.read"], valid_from="2000-01-01", valid_to="2000-12-31")
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid.uuid4(), grants=[expired])
    resp = await client.get("/v1/audit-events", headers=headers)
    assert resp.status_code == 403


async def test_malformed_grant_scope_is_401_not_422(
    client: httpx.AsyncClient, tenant_a: uuid.UUID
) -> None:
    # A validly-signed context whose grant carries a bad scope must collapse to the one
    # uniform 401, not leak a 422 from Scope validation (§5.8).
    bad = grant(["audit.read"], scope_type="galaxy")  # not a real scope type
    headers = actor_headers(tenant_id=tenant_a, user_id=uuid.uuid4(), grants=[bad])
    resp = await client.get("/v1/audit-events", headers=headers)
    assert resp.status_code == 401
