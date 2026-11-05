"""Activities preserves provenance, scope and complete signed page walks."""

import uuid

import pytest

from audit.tasks.consume import handle_event
from tests.api_support import actor_headers, grant
from tests.seed import audit_envelope


def headers(tenant, *, company=None):
    return actor_headers(
        tenant_id=tenant,
        user_id=uuid.uuid4(),
        grants=[
            grant(
                ["activity.read"],
                scope_type="company" if company else "tenant",
                scope_id=company,
            )
        ],
    )


@pytest.mark.parametrize(
    "actor_type,has_user", [("user", True), ("system", False), ("service_account", True)]
)
async def test_activity_retains_recorded_actor_and_source(
    client, session, tenant_a, actor_type, has_user
):
    company, principal, represented = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    envelope = audit_envelope(tenant_id=tenant_a, company_id=company)
    envelope = envelope.model_copy(
        update={
            "payload": {
                **envelope.payload,
                "actor_type": actor_type,
                "actor_user_id": str(principal) if has_user else None,
                "on_behalf_of_user_id": str(represented) if actor_type == "user" else None,
                "source_service": "identity",
            }
        }
    )
    await handle_event(session, envelope, consumer_name="activity-completeness")
    await session.commit()
    response = await client.get(
        "/v1/activity",
        params={"company_id": str(company)},
        headers=headers(tenant_a, company=company),
    )
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["actor_type"] == actor_type
    assert item["source_service"] == "identity"
    assert item["on_behalf_of_user_id"] == (str(represented) if actor_type == "user" else None)
    assert item["actor_user_id"] == (str(principal) if has_user else None)
    assert (
        not {"changes", "context", "reason", "actor_ip", "actor_user_agent", "row_hash"}
        & item.keys()
    )


async def test_tenant_feed_walk_includes_all_authorized_business_scopes_once(
    client, session, tenant_a, tenant_b
):
    company = uuid.uuid4()
    expected = []
    for tenant, category, scope in [
        (tenant_a, "admin", None),
        (tenant_a, "money", company),
        (tenant_a, "system", uuid.uuid4()),
        (tenant_a, "security", None),
        (tenant_b, "admin", company),
    ]:
        envelope = audit_envelope(tenant_id=tenant, category=category, company_id=scope)
        result = await handle_event(session, envelope, consumer_name="activity-completeness")
        if tenant == tenant_a and category != "security":
            expected.append(str(result.event_id))
    await session.commit()
    authority, cursor, seen = headers(tenant_a), None, []
    for _ in range(4):
        response = await client.get(
            "/v1/activity",
            params={"limit": 1, **({"cursor": cursor} if cursor else {})},
            headers=authority,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        seen.extend(row["id"] for row in body["items"])
        if not body["page"]["has_more"]:
            break
        cursor = body["page"]["next_cursor"]
    assert len(seen) == len(set(seen)) == len(expected)
    assert set(seen) == set(expected)
    denied = await client.get("/v1/activity", headers=headers(tenant_a, company=company))
    assert denied.status_code == 403


@pytest.mark.parametrize("change", [{"sort": "sequence"}, {"limit": 2}, {"company_id": None}])
async def test_activity_cursor_cannot_be_reused_for_another_query(
    client, session, tenant_a, change
):
    company = uuid.uuid4()
    for _ in range(3):
        await handle_event(
            session,
            audit_envelope(tenant_id=tenant_a, company_id=company),
            consumer_name="activity-completeness",
        )
    await session.commit()
    authority = headers(tenant_a)
    query = {"company_id": str(company), "limit": 1}
    first = await client.get("/v1/activity", params=query, headers=authority)
    cursor = first.json()["page"]["next_cursor"]
    changed = {
        key: value
        for key, value in {**query, **change, "cursor": cursor}.items()
        if value is not None
    }
    response = await client.get("/v1/activity", params=changed, headers=authority)
    assert response.status_code == 422
