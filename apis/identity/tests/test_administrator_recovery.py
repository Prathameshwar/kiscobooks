from __future__ import annotations

import datetime as dt
import json
import secrets
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from pydantic import SecretStr
from sqlalchemy import select

from identity.config import Settings
from identity.models import Outbox, RoleAssignment, Tenant, User
from identity.services.administrator_recovery import (
    AdministratorRecoveryProvider,
    AdministratorRecoveryUnavailableError,
)
from tests.test_gap_login import bearer

# Collecting the owning test module does not register its fixtures in this module.
from tests.test_platform_access import access_tenant, admin_detail  # noqa: F401
from tests.test_platform_setup import signed

pytest_plugins = ["tests.test_platform_access"]
SUBJECT = uuid.UUID("01900000-0000-7000-8000-000000000090")
TOKEN = "recovery_token_that_must_never_be_persisted"


def provider_settings():
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret=SecretStr(secrets.token_hex(32)),
        cursor_signing_secret=SecretStr(secrets.token_hex(32)),
        authentik_recovery_url="https://provider.test",
        authentik_recovery_token=SecretStr(secrets.token_hex(32)),
    )


def provider_user(**extra):
    return {
        "pk": 42,
        "uuid": str(SUBJECT),
        "email": "owner@example.com",
        "type": "external",
        "path": "bill/pending-registration",
        "is_active": True,
        "is_superuser": False,
        "groups": [],
        "roles": [],
        "attributes": {"billing_email_verified": True},
        **extra,
    }


@pytest.fixture
async def recovery_admin(client, access_tenant, factory, setup_app):  # noqa: F811
    key, _, tenant, owner = access_tenant
    app = setup_app[0]
    app.state.settings.authentik_recovery_url = "https://provider.test"
    app.state.settings.authentik_recovery_token = SecretStr(
        "restricted_credential_only_for_test_12345"
    )
    with tenant_scope(uuid.UUID(tenant)):
        async with factory() as db, db.begin():
            user = await db.get(User, uuid.UUID(owner))
            user.status = "active"
            user.authentik_sub = str(SUBJECT)
            user.updated_at = utcnow()
    detail = await admin_detail(client, key, tenant, owner)
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200, json={"results": [provider_user()], "pagination": {"next": 0}}
            )
        if request.url.path.endswith("recovery_email/"):
            return httpx.Response(204)
        return httpx.Response(
            200,
            json={
                "link": "https://provider.test/if/flow/bill-administrator-recovery/?flow_token="
                + TOKEN
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        previous = getattr(app.state, "oidc_http", None)
        app.state.oidc_http = http
        yield key, tenant, owner, detail, requests, app
        app.state.oidc_http = previous


def recovery_body(detail, **extra):
    return {
        "delivery": "link",
        "expected_updated_at": detail["updated_at"],
        "expected_assignment_updated_at": detail["assignment_updated_at"],
        "reason": "Administrator requested recovery",
        **extra,
    }


async def test_link_is_expiring_target_bound_and_never_saved(client, recovery_admin, factory):
    key, tenant, owner, detail, requests, _ = recovery_admin
    endpoint = f"/v1/platform/access/tenants/{tenant}/administrators/{owner}/password-recovery"
    response = await client.post(endpoint, headers=signed(key), json=recovery_body(detail))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["administrator_id"] == owner
    assert response.json()["recovery_url"].endswith(TOKEN)
    assert response.json()["delivery"] == "link"
    assert requests[0].url.params["uuid"] == str(SUBJECT)
    assert requests[1].url.path == "/api/v3/core/users/42/recovery/"
    assert json.loads(requests[1].content) == {"token_duration": "minutes=10"}
    replay = await client.post(
        endpoint,
        headers={**signed(key), "Idempotency-Key": "no-secret-receipt"},
        json=recovery_body(detail),
    )
    assert replay.status_code == 422 and len(requests) == 2
    async with factory() as db:
        with tenant_scope(uuid.UUID(tenant)):
            events = list(await db.scalars(select(Outbox)))
            assert any(event.event_type == "user.password_recovery_requested" for event in events)
            assert TOKEN not in str([event.payload for event in events])
            user = await db.get(User, uuid.UUID(owner))
            assert user.status == "active" and user.updated_at.isoformat() == detail[
                "updated_at"
            ].replace("Z", "+00:00")


async def test_email_uses_native_stage_and_returns_no_link(client, recovery_admin):
    key, tenant, owner, detail, requests, app = recovery_admin
    stage = uuid.uuid4()
    app.state.settings.authentik_recovery_email_stage = stage
    response = await client.post(
        f"/v1/platform/access/tenants/{tenant}/administrators/{owner}/password-recovery",
        headers=signed(key),
        json=recovery_body(detail, delivery="email"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["recovery_url"] is None
    assert response.json()["delivery"] == "email"
    assert requests[-1].url.path.endswith("/42/recovery_email/")
    assert json.loads(requests[-1].content) == {
        "token_duration": "minutes=10",
        "email_stage": str(stage),
    }


async def test_email_stays_disabled_without_configuration(client, recovery_admin):
    key, tenant, owner, detail, requests, _ = recovery_admin
    assert detail["recovery_deliveries"] == ["link"]
    response = await client.post(
        f"/v1/platform/access/tenants/{tenant}/administrators/{owner}/password-recovery",
        headers=signed(key),
        json=recovery_body(detail, delivery="email"),
    )
    assert response.status_code == 503
    assert requests == []


@pytest.mark.parametrize(
    "target",
    [
        "suspended_user",
        "invited",
        "deactivated",
        "revoked",
        "future_assignment",
        "expired_assignment",
        "suspended_tenant",
        "closed_tenant",
        "stale",
        "unbound",
        "unsupported_subject",
    ],
)
async def test_recovery_rechecks_target_and_revision(client, recovery_admin, factory, target):
    key, tenant, owner, detail, requests, _ = recovery_admin
    with tenant_scope(uuid.UUID(tenant)):
        async with factory() as db, db.begin():
            user = await db.get(User, uuid.UUID(owner))
            if target == "suspended_user":
                user.status = "suspended"
            if target in ("invited", "deactivated"):
                user.status = target
            if target == "unbound":
                user.authentik_sub = None
            if target == "unsupported_subject":
                user.authentik_sub = "external-subject-with-no-billing-recovery"
            if target == "stale":
                user.display_name = "New name"
            if target in ("revoked", "future_assignment", "expired_assignment"):
                assignment = await db.get(RoleAssignment, uuid.UUID(detail["assignment_id"]))
                if target == "revoked":
                    assignment.is_active = False
                if target == "future_assignment":
                    assignment.valid_from = utcnow().date() + dt.timedelta(days=1)
                if target == "expired_assignment":
                    assignment.valid_to = utcnow().date() - dt.timedelta(days=1)
            if target in ("suspended_tenant", "closed_tenant"):
                row = await db.get(Tenant, uuid.UUID(tenant))
                row.status = "closed" if target == "closed_tenant" else "suspended"
    if target != "stale":
        detail = await admin_detail(client, key, tenant, owner)
    if target in ("unbound", "unsupported_subject"):
        assert detail["recovery_deliveries"] == []
    response = await client.post(
        f"/v1/platform/access/tenants/{tenant}/administrators/{owner}/password-recovery",
        headers=signed(key),
        json=recovery_body(detail),
    )
    assert response.status_code == 409, response.text
    assert requests == []


async def test_recovery_checks_revoked_operator_authority(client, recovery_admin, factory):
    key, tenant, owner, detail, requests, _ = recovery_admin
    session = (await client.get("/v1/session", headers=signed(key))).json()
    with tenant_scope(uuid.UUID(session["tenant"]["id"])):
        async with factory() as db, db.begin():
            assignments = list(
                await db.scalars(
                    select(RoleAssignment).where(
                        RoleAssignment.subject_id == uuid.UUID(session["user"]["id"])
                    )
                )
            )
            for assignment in assignments:
                assignment.is_active = False
    response = await client.post(
        f"/v1/platform/access/tenants/{tenant}/administrators/{owner}/password-recovery",
        headers=signed(key),
        json=recovery_body(detail),
    )
    assert response.status_code == 403, response.text
    assert requests == []


async def test_recovery_requires_fresh_operator_and_closed_input(client, recovery_admin):
    import time

    key, tenant, owner, detail, requests, _ = recovery_admin
    endpoint = f"/v1/platform/access/tenants/{tenant}/administrators/{owner}/password-recovery"
    response = await client.post(
        endpoint,
        headers=bearer(
            key, email="admin@example.com", email_verified=True, auth_time=int(time.time()) - 301
        ),
        json=recovery_body(detail),
    )
    assert response.status_code == 403
    for extra in [
        {"reason": "  "},
        {"reason": "bad\nreason"},
        {"password": "should-never-be-accepted"},
        {"delivery": "sms"},
    ]:
        response = await client.post(
            endpoint, headers=signed(key), json=recovery_body(detail, **extra)
        )
        assert response.status_code == 422
    response = await client.post(
        endpoint.replace(owner, str(uuid.uuid4())), headers=signed(key), json=recovery_body(detail)
    )
    assert response.status_code == 404
    assert requests == []


@pytest.mark.parametrize(
    "override",
    [
        {"uuid": str(uuid.uuid4())},
        {"is_superuser": True},
        {"type": "service_account"},
        {"is_active": False},
        {"groups": [1]},
        {"roles": [1]},
        {"path": "users"},
        {"attributes": {}},
    ],
)
async def test_provider_rejects_privileged_or_wrong_accounts(override):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json={"results": [provider_user(**override)], "pagination": {"next": 0}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(AdministratorRecoveryUnavailableError):
            await AdministratorRecoveryProvider(provider_settings(), http).recover(
                SUBJECT, "link", "owner@example.com"
            )
    assert len(requests) == 1 and requests[0].method == "GET"


@pytest.mark.parametrize("subject", ["", "not-a-subject", "a" * 63, "F" * 64])
async def test_provider_rejects_unsupported_subject_without_http(subject):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(AdministratorRecoveryUnavailableError):
            await AdministratorRecoveryProvider(provider_settings(), http).recover(
                subject, "link", "owner@example.com"
            )
    assert requests == []


@pytest.mark.parametrize(
    "link",
    [
        "https://evil.test/if/flow/bill-administrator-recovery/?flow_token=" + TOKEN,
        "https://provider.test/if/flow/bill-administrator-recovery/?flow_token="
        + TOKEN
        + "&next=https://evil.test",
        "http://provider.test/if/flow/bill-administrator-recovery/?flow_token=" + TOKEN,
        "https://provider.test/if/flow/bill-administrator-recovery/?token=" + TOKEN,
    ],
)
async def test_untrusted_links_are_never_returned(link):
    def handler(request):
        return httpx.Response(
            200,
            json={"results": [provider_user()], "pagination": {"next": 0}}
            if request.method == "GET"
            else {"link": link},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(AdministratorRecoveryUnavailableError) as error:
            await AdministratorRecoveryProvider(provider_settings(), http).recover(
                SUBJECT, "link", "owner@example.com"
            )
        assert TOKEN not in str(error.value) and "evil.test" not in str(error.value)


@pytest.mark.parametrize("path", ["bill/pending-registration", "bill/tenant-administrators"])
async def test_opaque_subject_resolves_only_matching_account(path):
    subject = secrets.token_hex(32)
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            assert request.url.params["email"] == "owner@example.com"
            assert request.url.params["page_size"] == "2"
            return httpx.Response(
                200,
                json={
                    "results": [
                        provider_user(
                            uid=subject,
                            path=path,
                            attributes={
                                "billing_email_verified": True,
                                "billing_tenant_provision_command": str(uuid.uuid4()),
                            },
                        )
                    ],
                    "pagination": {"next": 0},
                },
            )
        return httpx.Response(
            200,
            json={
                "link": "https://provider.test/if/flow/bill-administrator-recovery/?flow_token="
                + TOKEN
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        link, _ = await AdministratorRecoveryProvider(provider_settings(), http).recover(
            subject, "link", "owner@example.com"
        )
    assert link.endswith(TOKEN)
    assert requests[-1].url.path == "/api/v3/core/users/42/recovery/"


@pytest.mark.parametrize(
    "fault",
    [
        "uid",
        "email",
        "duplicate",
        "next_page",
        "missing_pagination",
        "marker",
        "missing_roles",
        "missing_groups",
    ],
)
async def test_opaque_lookup_fails_closed_before_reset(fault):
    subject = secrets.token_hex(32)
    row = provider_user(
        uid=subject,
        path="bill/tenant-administrators",
        attributes={
            "billing_email_verified": True,
            "billing_tenant_provision_command": str(uuid.uuid4()),
        },
    )
    value = {"results": [row], "pagination": {"next": 0}}
    if fault == "uid":
        row["uid"] = secrets.token_hex(32)
    if fault == "email":
        row["email"] = "someone-else@example.com"
    if fault == "duplicate":
        value["results"].append(row.copy())
    if fault == "next_page":
        value["pagination"]["next"] = 2
    if fault == "missing_pagination":
        del value["pagination"]
    if fault == "marker":
        row["attributes"]["billing_tenant_provision_command"] = "not-a-command"
    if fault == "missing_roles":
        del row["roles"]
    if fault == "missing_groups":
        del row["groups"]
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=value)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(AdministratorRecoveryUnavailableError):
            await AdministratorRecoveryProvider(provider_settings(), http).recover(
                subject, "link", "owner@example.com"
            )
    assert len(requests) == 1 and requests[0].method == "GET"


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "http://provider.test",
        "https://user@provider.test",
        "https://provider.test/path",
        "https://provider.test/?query=x",
    ],
)
async def test_provider_configuration_refuses_untrusted_origins(origin):
    settings = provider_settings()
    settings.authentik_recovery_url = origin
    async with httpx.AsyncClient() as http:
        with pytest.raises(AdministratorRecoveryUnavailableError):
            AdministratorRecoveryProvider(settings, http)


@pytest.mark.parametrize("status", [302, 403, 500])
async def test_provider_http_failure_is_redacted_and_never_retried(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status, json={"private": TOKEN}, headers={"location": "https://untrusted.test"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(AdministratorRecoveryUnavailableError) as error:
            await AdministratorRecoveryProvider(provider_settings(), http).recover(
                SUBJECT, "link", "owner@example.com"
            )
    assert TOKEN not in str(error.value)
    assert len(requests) == 1


@pytest.mark.parametrize(
    "link",
    [
        None,
        "https://provider.test/\nunsafe",
        "https://provider.test/if/flow/bill-administrator-recovery/?flow_token=short",
        "https://provider.test/if/flow/bill-administrator-recovery/?flow_token="
        + TOKEN
        + "#fragment",
    ],
)
async def test_provider_rejects_malformed_secret_links(link):
    def handler(request):
        return httpx.Response(
            200,
            json={"results": [provider_user()], "pagination": {"next": 0}}
            if request.method == "GET"
            else {"link": link},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(AdministratorRecoveryUnavailableError):
            await AdministratorRecoveryProvider(provider_settings(), http).recover(
                SUBJECT, "link", "owner@example.com"
            )


@pytest.mark.parametrize("value", [None, 42, "not-a-uuid"])
def test_invalid_provision_markers(value):
    assert not AdministratorRecoveryProvider.valid_provision_marker(value)
