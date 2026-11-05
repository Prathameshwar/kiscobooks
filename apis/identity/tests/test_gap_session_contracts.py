from __future__ import annotations

import base64
import json
import uuid

import pytest
from billing_platform.authz import Grant, Scope
from billing_platform.constants import SCOPE_ALL
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.errors import ValidationFailedError
from fastapi import Request
from sqlalchemy import select

from identity.api.auth import Actor
from identity.api.login import gateway_authorize
from identity.models import Company, User
from tests.api_support import actor_headers, grant
from tests.factories import build_user, seed_two_companies


async def test_session_selection_preferences_and_admin_revocation(
    client, session, tenant_a, tenant_b
):
    company_id, foreign = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        user = build_user(tenant_id=tenant_a, default_company_id=company_id)
        target = build_user(tenant_id=tenant_a, email="target@example.test")
        session.add_all([user, target])
        await session.commit()
        user_id, target_id = user.id, target.id
    headers = actor_headers(
        tenant_id=tenant_a, user_id=user_id, grants=[grant(["company.read", "user.update"])]
    )
    response = await client.get("/v1/session", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["company"]["id"] == str(company_id)
    explicit = await client.get(f"/v1/session?company_id={company_id}", headers=headers)
    assert explicit.json()["company"]["id"] == str(company_id)
    assert (await client.get(f"/v1/session?company_id={foreign}", headers=headers)).json()[
        "company"
    ] is None
    denied = actor_headers(tenant_id=tenant_a, user_id=user_id)
    assert (await client.get("/v1/session", headers=denied)).json()["company"] is None
    assert (
        await client.get(f"/v1/session?company_id={company_id}", headers=denied)
    ).status_code == 403
    with tenant_scope(tenant_a):
        company = await session.get(Company, company_id)
        company.requires_step_up = True
        await session.commit()
    assert (await client.get("/v1/session", headers=headers)).json()["company"] is None
    assert (
        await client.get(f"/v1/session?company_id={company_id}", headers=headers)
    ).status_code == 403
    gateway = await client.get(
        "/internal/v1/gateway/authorize",
        headers={
            **headers,
            "x-original-uri": f"/api/catalog/v1/companies/{company_id}/items?limit=1",
        },
    )
    assert gateway.status_code == 403
    with tenant_scope(tenant_a):
        company.requires_step_up = False
        company.status = "inactive"
        await session.commit()
    assert (await client.get("/v1/session", headers=headers)).json()["company"] is None
    path = "/v1/session/preferences"
    assert (
        await client.patch(path, headers=headers, json={"timezone": "No/Such_Zone"})
    ).status_code == 422
    for _ in range(2):
        result = await client.patch(path, headers=headers, json={"timezone": "Asia/Kolkata"})
        assert result.status_code == 200, result.text
    with tenant_scope(tenant_a):
        events = list(
            await session.scalars(
                select(Outbox).where(Outbox.event_type == "user.preferences_updated")
            )
        )
        assert len(events) == 1
    assert (
        await client.post(
            f"/v1/users/{target_id}/revoke-sessions", headers=denied, json={"reason": "lost device"}
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/v1/users/{uuid.uuid4()}/revoke-sessions",
            headers=headers,
            json={"reason": "lost device"},
        )
    ).status_code == 404
    result = await client.post(
        f"/v1/users/{target_id}/revoke-sessions", headers=headers, json={"reason": "lost device"}
    )
    assert result.status_code == 204, result.text
    with tenant_scope(tenant_a):
        session.expire_all()
        assert (await session.get(User, target_id)).tokens_valid_after_at is not None
    missing = actor_headers(tenant_id=tenant_a, user_id=uuid.uuid4())
    assert (await client.get("/v1/session", headers=missing)).status_code == 404


async def test_gateway_support_attribution_and_transport_bound(app):
    from pydantic import SecretStr

    app.state.settings.actor_signing_secret = SecretStr("ephemeral-gateway-test-secret")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/internal/v1/gateway/authorize",
            "headers": [],
            "app": app,
        }
    )
    current = Actor(
        uuid.uuid4(),
        uuid.uuid4(),
        real_user_id=uuid.uuid4(),
        impersonation_id=uuid.uuid4(),
        impersonation_expires_at=123,
    )
    response = await gateway_authorize(request, current)
    encoded = response.headers["x-actor-context"]
    body = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert body["actor_user_id"] == str(current.real_user_id)
    assert body["impersonation_id"] == str(current.impersonation_id)
    assert response.headers["cache-control"] == "no-store"
    current.grants = tuple(
        Grant(frozenset({"company.read"}), Scope("tenant", SCOPE_ALL), utcnow().date())
        for _ in range(256)
    )
    with pytest.raises(ValidationFailedError, match="transport bound"):
        await gateway_authorize(request, current)


@pytest.mark.parametrize("timezone", ["/etc/passwd", "../Europe/London", ""])
async def test_invalid_timezone_paths_return_validation_error(
    app, session, tenant_a, tenant_b, timezone
):
    import httpx

    await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        user = build_user(tenant_id=tenant_a)
        session.add(user)
        await session.commit()
    headers = actor_headers(tenant_id=tenant_a, user_id=user.id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://identity.test",
    ) as client:
        response = await client.patch(
            "/v1/session/preferences", headers=headers, json={"timezone": timezone}
        )
    assert response.status_code == 422, response.text


async def test_gateway_malformed_company_id_returns_validation_error(app):
    import httpx

    headers = actor_headers(tenant_id=uuid.uuid4(), user_id=uuid.uuid4())
    headers["x-original-uri"] = "/api/catalog/v1/companies/" + "-" * 36 + "/items"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://identity.test",
    ) as client:
        response = await client.get("/internal/v1/gateway/authorize", headers=headers)
    assert response.status_code == 422, response.text


async def test_token_admin_revocation_is_scoped_and_idempotent(client, session, tenant_a, tenant_b):
    from tests.factories import build_user_api_token

    await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        owner = build_user(tenant_id=tenant_a)
        admin = build_user(tenant_id=tenant_a, email="admin@example.test")
        session.add_all([owner, admin])
        await session.flush()
        token = build_user_api_token(tenant_id=tenant_a, user_id=owner.id)
        session.add(token)
        await session.commit()
    denied = actor_headers(tenant_id=tenant_a, user_id=admin.id)
    headers = actor_headers(tenant_id=tenant_a, user_id=admin.id, grants=[grant(["user.update"])])
    root = f"/v1/api-tokens/{token.id}/revoke"
    assert (await client.post(root, headers=denied, json={"reason": "rotation"})).status_code == 403
    foreign = actor_headers(
        tenant_id=tenant_b, user_id=uuid.uuid4(), grants=[grant(["user.update"])]
    )
    assert (
        await client.post(root, headers=foreign, json={"reason": "rotation"})
    ).status_code == 404
    first = await client.post(root, headers=headers, json={"reason": "rotation"})
    assert first.status_code == 200, first.text
    second = await client.post(root, headers=headers, json={"reason": "rotation"})
    assert second.json() == first.json()
    with tenant_scope(tenant_a):
        events = list(
            await session.scalars(
                select(Outbox).where(Outbox.event_type == "user.api_token_revoked")
            )
        )
        assert len(events) == 1
