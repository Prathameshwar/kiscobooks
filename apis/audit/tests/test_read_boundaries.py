import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from audit.tasks.consume import handle_event
from tests.api_support import actor_headers, grant
from tests.seed import audit_envelope


@pytest.mark.parametrize(
    "query",
    [
        "limit=1&limit=2",
        "unrecognized=yes",
        "occurred_from=2026-01-01T00:00:00&occurred_to=2026-02-01T00:00:00Z",
    ],
)
async def test_invalid_queries_use_safe_error_envelope(
    client: httpx.AsyncClient, tenant_a: uuid.UUID, query: str
) -> None:
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid.uuid4(), grants=[grant(["audit.read"])]
    )
    response = await client.get("/v1/audit-events?" + query, headers=headers)
    assert response.status_code == 422
    assert set(response.json()) == {"error"}
    assert response.headers["cache-control"] == "no-store"


async def test_cursor_cannot_cross_user_or_query(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    async with factory() as db, db.begin():
        for _ in range(3):
            await handle_event(db, audit_envelope(tenant_id=tenant_a), consumer_name="cursor-test")
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid.uuid4(), grants=[grant(["audit.read"])]
    )
    first = await client.get("/v1/audit-events?limit=1", headers=headers)
    cursor = first.json()["page"]["next_cursor"]
    assert cursor
    params = {"limit": 1, "cursor": cursor}
    assert (await client.get("/v1/audit-events", params=params, headers=headers)).status_code == 200
    assert (
        await client.get("/v1/audit-events", params=params | {"category": "admin"}, headers=headers)
    ).status_code == 422
    other = actor_headers(tenant_id=tenant_a, user_id=uuid.uuid4(), grants=[grant(["audit.read"])])
    assert (await client.get("/v1/audit-events", params=params, headers=other)).status_code == 422


async def test_unexpected_database_failure_has_safe_uncached_envelope(app, tenant_a):
    from unittest.mock import MagicMock

    app.state.session_factory = MagicMock(side_effect=RuntimeError("private database details"))
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://audit.test") as http:
        response = await http.get(
            "/v1/audit-events",
            headers=actor_headers(
                tenant_id=tenant_a,
                user_id=uuid.uuid4(),
                grants=[grant(["audit.read"])],
            ),
        )
    assert response.status_code == 500
    assert response.headers.get("cache-control") == "no-store"
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Audit request failed"}
    }
    assert "private" not in response.text


@pytest.mark.parametrize("surface", ["audit-events", "activity"])
async def test_broad_admin_can_paginate_live_read_surface(client, factory, tenant_a, surface):
    async with factory() as db, db.begin():
        for _ in range(3):
            await handle_event(db, audit_envelope(tenant_id=tenant_a), consumer_name="broad-cursor")
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid.uuid4(),
        grants=[
            grant(["audit.read", "activity.read"] + [f"resource_{i}.read" for i in range(200)])
        ],
    )
    first = await client.get(f"/v1/{surface}?limit=1", headers=headers)
    assert first.status_code == 200, first.text
    cursor = first.json()["page"]["next_cursor"]
    assert cursor and len(cursor) < 1024
    second = await client.get(
        f"/v1/{surface}", params={"limit": 1, "cursor": cursor}, headers=headers
    )
    assert second.status_code == 200, second.text
    assert second.json()["items"][0]["id"] != first.json()["items"][0]["id"]
