"""Further read-surface coverage: activity feed, pagination, scoped detail, scheduler."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from audit.tasks.consume import handle_event
from audit.tasks.scheduler import run_chain_verification
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


# -- activity feed ----------------------------------------------------------------------


async def test_activity_requires_its_permission(
    client: httpx.AsyncClient, tenant_a: uuid.UUID
) -> None:
    resp = await client.get("/v1/activity", headers=_headers(tenant_a, ["audit.read"]))
    assert resp.status_code == 403


async def test_activity_returns_non_security_events(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed(session, tenant_a, category="admin", action="created")
    await _seed(session, tenant_a, category="security", action="logged_in")

    resp = await client.get("/v1/activity", headers=_headers(tenant_a, ["activity.read"]))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items
    assert all(i["category"] != "security" for i in items)


# -- keyset pagination ------------------------------------------------------------------


async def test_cursor_walks_every_row_once(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    for _ in range(3):
        await _seed(session, tenant_a, category="admin")

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(5):  # generous upper bound; the loop breaks when the page is exhausted
        url = f"/v1/audit-events?limit=1{f'&cursor={cursor}' if cursor else ''}"
        resp = await client.get(url, headers=_headers(tenant_a, ["audit.read"]))
        assert resp.status_code == 200
        body = resp.json()
        seen.extend(i["id"] for i in body["items"])
        cursor = body["page"]["next_cursor"]
        if not body["page"]["has_more"]:
            break

    assert len(seen) == 3
    assert len(set(seen)) == 3  # no row repeated across page boundaries


async def test_valid_category_filter_narrows_results(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed(session, tenant_a, category="admin")
    await _seed(session, tenant_a, category="money")

    resp = await client.get(
        "/v1/audit-events?category=money", headers=_headers(tenant_a, ["audit.read"])
    )
    assert resp.status_code == 200
    assert all(i["category"] == "money" for i in resp.json()["items"])


async def test_unknown_category_filter_is_422(
    client: httpx.AsyncClient, tenant_a: uuid.UUID
) -> None:
    resp = await client.get(
        "/v1/audit-events?category=bogus", headers=_headers(tenant_a, ["audit.read"])
    )
    assert resp.status_code == 422


# -- typed filters (api-conventions §list) ----------------------------------------------


async def test_typed_filters_narrow_the_trail(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    wanted = uuid.uuid4()
    await _seed(
        session, tenant_a, category="admin", action="created",
        entity_type="invoice", entity_id=wanted,
    )
    await _seed(session, tenant_a, category="admin", action="deleted", entity_type="user")

    resp = await client.get(
        f"/v1/audit-events?entity_type=invoice&entity_id={wanted}&action=created"
        "&occurred_from=2000-01-01T00:00:00%2B00:00&occurred_to=2100-01-01T00:00:00%2B00:00",
        headers=_headers(tenant_a, ["audit.read"]),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["entity_type"] == "invoice"
    assert items[0]["entity_id"] == str(wanted)


# -- detail: category- and scope-gated --------------------------------------------------


async def test_security_event_detail_needs_read_security(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed(session, tenant_a, category="security", action="logged_in")
    # Find it via the security surface to get id + occurred_at.
    listed = await client.get(
        "/v1/audit-events/security", headers=_headers(tenant_a, ["audit.read_security"])
    )
    item = listed.json()["items"][0]
    path = f"/v1/audit-events/{item['id']}?occurred_at={item['occurred_at']}"

    # audit.read is not enough for a security-category row (§5.1). It returns 404, not 403,
    # so the endpoint is not an existence oracle for security events.
    denied = await client.get(path, headers=_headers(tenant_a, ["audit.read"]))
    assert denied.status_code == 404
    allowed = await client.get(path, headers=_headers(tenant_a, ["audit.read_security"]))
    assert allowed.status_code == 200


async def test_department_scoped_detail_check(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    company, department = uuid.uuid4(), uuid.uuid4()
    await _seed(session, tenant_a, company_id=company, department_id=department)

    # A department-scope grant reaches the row (company + department in its path).
    headers = _headers(
        tenant_a, ["audit.read"], scope_type="department", scope_id=department
    )
    listed = await client.get(
        f"/v1/audit-events?company_id={company}",
        headers=_headers(tenant_a, ["audit.read"], scope_type="company", scope_id=company),
    )
    item = listed.json()["items"][0]
    resp = await client.get(
        f"/v1/audit-events/{item['id']}?occurred_at={item['occurred_at']}", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["department_id"] == str(department)


# -- scheduler wrapper ------------------------------------------------------------------


async def test_scheduler_chain_verification_reports_clean(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed(session, tenant_a)
    assert await run_chain_verification(session) == {}
