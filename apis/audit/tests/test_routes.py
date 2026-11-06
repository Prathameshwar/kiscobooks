"""HTTP tests for the audit read surfaces (docs/audit.md §1, §5; CLAUDE.md §7 matrix)."""

from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.db.platform_models import Outbox
from billing_platform.db.tenant_context import unfiltered
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from audit.tasks.consume import handle_event
from tests.api_support import actor_headers, grant
from tests.seed import audit_envelope

pytestmark = pytest.mark.asyncio

_CONSUMER = "audit-consumer"
_USER = uuid.uuid4()


async def _seed(session: AsyncSession, tenant: uuid.UUID, **kwargs: object) -> None:
    await handle_event(session, audit_envelope(tenant_id=tenant, **kwargs), consumer_name=_CONSUMER)  # type: ignore[arg-type]
    await session.commit()


def _headers(tenant: uuid.UUID, permissions: list[str], **grant_kwargs: object) -> dict[str, str]:
    return actor_headers(
        tenant_id=tenant, user_id=_USER, grants=[grant(permissions, **grant_kwargs)]  # type: ignore[arg-type]
    )


# -- authentication / authorization gate ------------------------------------------------


async def test_unauthenticated_is_401(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/audit-events")
    assert resp.status_code == 401


async def test_permitted_but_no_grant_is_403(
    client: httpx.AsyncClient, tenant_a: uuid.UUID
) -> None:
    # A valid actor context holding an unrelated permission — the trail requires audit.read.
    headers = _headers(tenant_a, ["activity.read"])
    resp = await client.get("/v1/audit-events", headers=headers)
    assert resp.status_code == 403


async def test_bad_sort_field_is_422(client: httpx.AsyncClient, tenant_a: uuid.UUID) -> None:
    headers = _headers(tenant_a, ["audit.read"])
    resp = await client.get("/v1/audit-events?sort=actor_ip", headers=headers)
    assert resp.status_code == 422


async def test_limit_over_max_is_422(client: httpx.AsyncClient, tenant_a: uuid.UUID) -> None:
    headers = _headers(tenant_a, ["audit.read"])
    resp = await client.get("/v1/audit-events?limit=500", headers=headers)
    assert resp.status_code == 422


# -- happy path + category separation ---------------------------------------------------


async def test_trail_lists_non_security_events(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed(session, tenant_a, category="admin", action="created")
    await _seed(session, tenant_a, category="security", action="logged_in")

    resp = await client.get("/v1/audit-events", headers=_headers(tenant_a, ["audit.read"]))
    assert resp.status_code == 200
    items = resp.json()["items"]
    categories = {i["category"] for i in items}
    assert "admin" in categories
    assert "security" not in categories  # security is gated separately (§5.1)


async def test_security_surface_requires_its_own_permission(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed(session, tenant_a, category="security", action="logged_in")

    denied = await client.get(
        "/v1/audit-events/security", headers=_headers(tenant_a, ["audit.read"])
    )
    assert denied.status_code == 403

    allowed = await client.get(
        "/v1/audit-events/security", headers=_headers(tenant_a, ["audit.read_security"])
    )
    assert allowed.status_code == 200
    assert all(i["category"] == "security" for i in allowed.json()["items"])


async def test_category_security_on_trail_is_422(
    client: httpx.AsyncClient, tenant_a: uuid.UUID
) -> None:
    resp = await client.get(
        "/v1/audit-events?category=security", headers=_headers(tenant_a, ["audit.read"])
    )
    assert resp.status_code == 422


# -- object-level scope (CLAUDE.md §5.2) ------------------------------------------------


async def test_company_scoped_reader_cannot_read_another_company(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _seed(session, tenant_a, company_id=company_a)

    headers = _headers(tenant_a, ["audit.read"], scope_type="company", scope_id=company_a)
    # Their own company: allowed.
    own = await client.get(f"/v1/audit-events?company_id={company_a}", headers=headers)
    assert own.status_code == 200
    # Another company: 403, even though they hold audit.read.
    other = await client.get(f"/v1/audit-events?company_id={company_b}", headers=headers)
    assert other.status_code == 403
    # Tenant-wide (no company named) needs a tenant-scope grant: 403.
    wide = await client.get("/v1/audit-events", headers=headers)
    assert wide.status_code == 403


# -- cross-tenant isolation (CLAUDE.md §7) ----------------------------------------------


async def test_trail_never_shows_another_tenants_rows(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await _seed(session, tenant_a, action="a-event")
    await _seed(session, tenant_b, action="b-event")

    resp = await client.get("/v1/audit-events", headers=_headers(tenant_a, ["audit.read"]))
    assert resp.status_code == 200
    actions = {i["action"] for i in resp.json()["items"]}
    assert "a-event" in actions
    assert "b-event" not in actions  # tenant_b is invisible to tenant_a


# -- detail -----------------------------------------------------------------------------


async def test_detail_returns_changes_and_chain_proof(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed(session, tenant_a, changes={"name": {"from": "a", "to": "b"}})
    listed = await client.get("/v1/audit-events", headers=_headers(tenant_a, ["audit.read"]))
    item = listed.json()["items"][0]

    resp = await client.get(
        f"/v1/audit-events/{item['id']}?occurred_at={item['occurred_at']}",
        headers=_headers(tenant_a, ["audit.read"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["changes"] == {"name": {"from": "a", "to": "b"}}
    assert len(body["row_hash"]) == 64  # hex of BINARY(32)


async def test_detail_missing_is_404(client: httpx.AsyncClient, tenant_a: uuid.UUID) -> None:
    resp = await client.get(
        f"/v1/audit-events/{uuid.uuid4()}?occurred_at=2026-09-11T12:00:00%2B00:00",
        headers=_headers(tenant_a, ["audit.read"]),
    )
    assert resp.status_code == 404


# -- export is itself audited (§5.3) ----------------------------------------------------


async def test_export_records_an_access_event_on_the_outbox(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed(session, tenant_a, category="admin")

    resp = await client.post(
        "/v1/audit-events/export", headers=_headers(tenant_a, ["audit.export"])
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["truncated"] is False

    # The export staged one audit-export event on the outbox (§5.3), to flow back through
    # the single chain writer rather than being written straight to audit_event.
    with unfiltered():
        staged = await session.scalar(
            select(func.count(Outbox.id)).where(Outbox.event_type == "audit.exported")
        )
    assert staged == 1


async def test_export_denied_without_permission(
    client: httpx.AsyncClient, tenant_a: uuid.UUID
) -> None:
    resp = await client.post(
        "/v1/audit-events/export", headers=_headers(tenant_a, ["audit.read"])
    )
    assert resp.status_code == 403


# -- integration logs ------------------------------------------------------------------


async def test_deferred_integration_logs_are_not_mounted(
    client: httpx.AsyncClient, tenant_a: uuid.UUID
) -> None:
    payload = {
        "integration_name": "netsuite_export",
        "direction": "outbound",
        "status": "success",
        "response_code": 200,
        "retry_count": 0,
        "error_message": None,
        "metadata_json": {"records": 42},
    }
    headers = _headers(tenant_a, ["audit.read"])
    assert (await client.post("/v1/integration-logs", json=payload, headers=headers)).status_code == 404
    assert (await client.get("/v1/integration-logs", headers=headers)).status_code == 404
    assert (
        await client.get(
            f"/v1/integration-logs/{uuid.uuid4()}?occurred_at=2026-11-05T00:00:00Z",
            headers=headers,
        )
    ).status_code == 404

