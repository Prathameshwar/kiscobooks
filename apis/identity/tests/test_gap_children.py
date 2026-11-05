from __future__ import annotations

import uuid

import httpx
from billing_platform.db.platform_models import Outbox
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api_support import actor_headers, grant
from tests.factories import build_user, seed_two_companies


async def test_contacts_scope_primary_lifecycle_and_redaction(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, other = await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["company.read", "company.update"], scope_type="company", scope_id=company)],
    )
    url = f"/v1/companies/{company}/contacts"
    body = {
        "type": "finance",
        "name": "Private Person",
        "email": "private@example.test",
        "is_primary": True,
    }
    first = await client.post(url, headers=headers, json=body)
    second = await client.post(url, headers=headers, json=body)
    assert first.status_code == second.status_code == 201
    cid = second.json()["id"]
    rows = (await client.get(url, headers=headers)).json()["items"]
    assert sum(row["is_primary"] for row in rows) == 1
    assert (
        await client.put(
            url + "/" + cid, headers=headers, json={**body, "name": "New private name"}
        )
    ).status_code == 200
    for _ in range(2):
        assert (
            await client.post(
                url + "/" + cid + "/lifecycle",
                headers=headers,
                json={"is_active": False, "reason": "retired"},
            )
        ).status_code == 200
    assert (await client.put(url + "/" + cid, headers=headers, json=body)).status_code == 409
    assert (
        await client.get(f"/v1/companies/{other}/contacts/{cid}", headers=headers)
    ).status_code == 403
    assert (await client.get(url)).status_code == 401
    assert (
        await client.post(url, headers=headers, json={**body, "email": "bad"})
    ).status_code == 422
    with tenant_scope(tenant_a):
        events = list(
            await session.scalars(select(Outbox).where(Outbox.event_type.like("company.contact%")))
        )
        assert len(events) == 5
        assert "private" not in str([e.payload for e in events]).lower()


async def test_preferences_versions_replay_and_authority(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    uid = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=uid))
        await session.commit()
    headers = actor_headers(tenant_id=tenant_a, user_id=uid)
    url = f"/v1/users/{uid}/notification-preferences/invoice.posted/email"
    for enabled, version in [(False, 1), (False, 1), (True, 2)]:
        response = await client.put(url, headers=headers, json={"is_enabled": enabled})
        assert response.status_code == 200, response.text
        assert response.json()["source_version"] == version
    assert (
        len(
            (await client.get(f"/v1/users/{uid}/notification-preferences", headers=headers)).json()[
                "items"
            ]
        )
        == 1
    )
    outsider = actor_headers(tenant_id=tenant_a, user_id=uuid7())
    assert (await client.put(url, headers=outsider, json={"is_enabled": False})).status_code == 403
    assert (
        await client.put(
            url.replace("invoice.posted", "user.invitation"),
            headers=headers,
            json={"is_enabled": False},
        )
    ).status_code == 422
    assert (await client.put(url, headers=headers, json={"is_enabled": "true"})).status_code == 422
    with tenant_scope(tenant_a):
        events = list(
            await session.scalars(
                select(Outbox).where(Outbox.event_type == "user_notification_preference.changed")
            )
        )
        assert [e.payload["source_version"] for e in events] == [1, 2]
