import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models.masters import AccountHead
from tests.conftest import COMPANY, TENANT, headers

BASE = f"/v1/companies/{COMPANY}"


async def test_setup_auth_idempotency_and_audit(client: httpx.AsyncClient, app: FastAPI) -> None:
    assert (await client.get("/health/live")).status_code == 200
    # Native fixtures run the real migrations; SQLite fixtures have no revision table.
    expected_readiness = 200 if app.state.engine.dialect.name == "mysql" else 503
    assert (await client.get("/health/ready")).status_code == expected_readiness
    assert (await client.get(BASE + "/account-heads")).status_code == 401
    assert (
        await client.get(BASE + "/account-heads", headers=headers(permissions=set()))
    ).status_code == 403
    h = headers()
    first = await client.post(BASE + "/accounting-setup/initialize", json={}, headers=h)
    assert first.status_code == 200, first.text
    replay = await client.post(BASE + "/accounting-setup/initialize", json={}, headers=h)
    assert replay.status_code == 200, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    response = await client.get(BASE + "/account-heads", headers=headers())
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 5
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert len(list(await db.scalars(select(AccountHead)))) == 5
            events = list(await db.scalars(select(Outbox)))
            # Five heads, 28 groups, 12 accounts, setup create/update, template and source capture.
            assert len(events) == 49
            assert sum(event.event_type == "accounting.reporting.captured" for event in events) == 1


async def test_group_create(client: httpx.AsyncClient) -> None:
    result = await client.post(BASE + "/accounting-setup/initialize", json={}, headers=headers())
    assert result.status_code == 200, result.text
    head = (await client.get(BASE + "/account-heads", headers=headers())).json()["items"][0]["id"]
    created = await client.post(
        BASE + "/account-groups",
        json={"code": "GROUP", "name": "Example", "head_id": head},
        headers=headers(),
    )
    assert created.status_code == 201, created.text
