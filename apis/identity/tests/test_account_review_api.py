import secrets
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from billing_platform.db import tenant_scope, unfiltered
from sqlalchemy import select

from identity.models import AccountReviewCommand, Outbox, RoleAssignment, Tenant, User
from identity.services.account_provider import AccountProviderUnavailableError
from tests.test_account_review_domain import applicant
from tests.test_gap_login import bearer
from tests.test_platform_setup import BODY, signed

pytest_plugins = ["tests.test_platform_setup"]


@pytest.fixture
async def review_app(setup_app, client):
    app, key, access = setup_app
    result = await client.post("/v1/setup/complete", json=BODY, headers={**access, **signed(key)})
    assert result.status_code == 200
    app.state.settings.authentik_review_url = "https://provider.test"
    from pydantic import SecretStr

    app.state.settings.authentik_review_token = SecretStr(secrets.token_urlsafe(32))
    return app, key, uuid.UUID(result.json()["tenant_id"])


async def test_import_review_readback_and_replay(review_app, client, factory):
    _, key, tenant = review_app
    observed = applicant()
    from tests.factories import build_user, build_user_invitation

    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            invited = build_user(tenant_id=tenant, email=observed.email, status="invited")
            db.add(invited)
            await db.flush()
            invitation = build_user_invitation(tenant_id=tenant, user_id=invited.id)
            db.add(invitation)
            invitation_id = invitation.id
    with patch(
        "identity.services.account_provider.AccountProvider.page",
        AsyncMock(return_value=([observed], False)),
    ):
        assert (
            await client.post("/v1/platform/accounts/sync", headers=signed(key))
        ).status_code == 200
    listing = await client.get("/v1/platform/accounts", headers=signed(key))
    assert listing.status_code == 200, listing.text
    row = listing.json()["items"][0]
    before = await client.get("/v1/platform/accounts/" + row["id"], headers=signed(key))
    assert before.json()["version"] == 1
    body = {
        "action": "approve",
        "version": 1,
        "reason": "Reviewed identity independently",
        "attested": True,
    }
    headers = {**signed(key), "Idempotency-Key": secrets.token_hex(10)}
    approved = applicant(provider_uuid=observed.provider_uuid, is_active=True, verified=True)

    async def read(self, provider_id):
        with tenant_scope(tenant):
            async with factory() as db:
                command = await db.scalar(select(AccountReviewCommand))
                tag = str(command.id) if getattr(read, "changed", False) else None
        return (approved if tag else observed), {
            "attributes": {"billing_account_review_command": tag}
        }

    async def apply(*args, **kwargs):
        read.changed = True

    with (
        patch("identity.services.account_provider.AccountProvider.read", read),
        patch("identity.services.account_provider.AccountProvider.apply", apply),
    ):
        result = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/review", json=body, headers=headers
        )
        assert result.status_code == 202, result.text
        assert (
            result.json()["status"] == "approved"
            and result.json()["history"][0]["status"] == "completed"
        )
        assert result.json()["handoff"]["notification_status"] == "manual"
        assert result.json()["handoff"]["invitation_url"] == (
            f"https://auth.test/accept?tenant={tenant}&invitation={invitation_id}"
        )
        replay = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/review", json=body, headers=headers
        )
        assert replay.json()["status"] == "approved"
    with tenant_scope(tenant):
        async with factory() as db:
            assert len(list(await db.scalars(select(AccountReviewCommand)))) == 1
            assert (
                len(
                    list(
                        await db.scalars(
                            select(Outbox).where(
                                Outbox.event_type.like("platform.account_decision%")
                            )
                        )
                    )
                )
                == 2
            )
    assert (await client.get("/v1/platform/accounts")).status_code == 401
    assert (
        await client.get("/v1/platform/accounts", headers=signed(key, subject="other"))
    ).status_code in [401, 403]


async def test_public_registration_approval_provisions_one_admin_tenant(
    review_app, client, factory
):
    app, key, operating_tenant = review_app
    from pydantic import SecretStr

    app.state.settings.notification_platform_tenant_id = operating_tenant
    app.state.settings.notification_platform_space_id = uuid.uuid4()
    app.state.settings.notification_platform_encryption_key = SecretStr(secrets.token_urlsafe(32))
    observed = applicant(workspace_name="North Books", state_code="")
    with patch(
        "identity.services.account_provider.AccountProvider.page",
        AsyncMock(return_value=([observed], False)),
    ):
        assert (
            await client.post("/v1/platform/accounts/sync", headers=signed(key))
        ).status_code == 200
    row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]
    approved = applicant(
        provider_uuid=observed.provider_uuid,
        workspace_name="North Books",
        state_code="",
        is_active=True,
        verified=True,
    )
    command_id = None
    provider_subject = secrets.token_hex(32)

    async def read(self, provider_id):
        result = approved if command_id else observed
        return result, {
            "uid": provider_subject,
            "attributes": {"billing_account_review_command": command_id},
        }

    async def apply(*args, **kwargs):
        nonlocal command_id
        command_id = str(kwargs["command_id"])

    headers = {**signed(key), "Idempotency-Key": secrets.token_hex(10)}
    body = {
        "action": "approve",
        "version": 1,
        "reason": "Independently verified applicant and address",
        "attested": True,
    }
    with (
        patch("identity.services.account_provider.AccountProvider.read", read),
        patch("identity.services.account_provider.AccountProvider.apply", apply),
    ):
        result = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/review", json=body, headers=headers
        )
        assert result.status_code == 202, result.text
        assert result.json()["status"] == "approved"
        assert result.json()["handoff"]["username"] == observed.username
        assert result.json()["handoff"]["sign_in_url"] == "https://auth.test/login"
        assert result.json()["handoff"]["notification_status"] == "queued"
        replay = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/review", json=body, headers=headers
        )
        assert replay.status_code == 202
    with tenant_scope(operating_tenant):
        async with factory() as db:
            ready = list(
                await db.scalars(
                    select(Outbox).where(
                        Outbox.event_type == "identity.platform_notification.requested",
                        Outbox.aggregate_id == uuid.UUID(row["id"]),
                    )
                )
            )
            assert len(ready) == 1
            assert ready[0].payload["use_case"] == "tenant.administrator.ready"
            import base64
            import hashlib
            import json

            from billing_platform.crypto import AesGcmCipher

            settings = app.state.settings
            cipher = AesGcmCipher(
                hashlib.sha256(
                    settings.notification_platform_encryption_key.get_secret_value().encode()
                ).digest()
            )
            content = json.loads(
                cipher.decrypt(
                    base64.b64decode(ready[0].payload["encrypted_payload"]),
                    associated_data=ready[0].message_id.bytes
                    + settings.notification_platform_space_id.bytes
                    + b"tenant.administrator.ready",
                )
            )
            assert content == {
                "destinations": {"email": observed.email},
                "variables": {
                    "username": observed.username,
                    "sign_in_url": "https://auth.test/login",
                },
            }
    with unfiltered():
        async with factory() as db:
            user = await db.scalar(select(User).where(User.authentik_sub == provider_subject))
            assert user is not None and user.status == "active" and user.email_verified_at
            tenant = await db.get(Tenant, user.tenant_id)
            assert tenant is not None and tenant.name == "North Books"
            assignments = list(
                await db.scalars(select(RoleAssignment).where(RoleAssignment.subject_id == user.id))
            )
            assert len(assignments) == 1 and assignments[0].is_active


async def test_invalid_oidc_subject_never_activates_public_signup(review_app, client):
    _, key, _ = review_app
    observed = applicant(workspace_name="North Books", state_code="")
    with patch(
        "identity.services.account_provider.AccountProvider.page",
        AsyncMock(return_value=([observed], False)),
    ):
        await client.post("/v1/platform/accounts/sync", headers=signed(key))
    row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]
    mutation = AsyncMock()
    with (
        patch(
            "identity.services.account_provider.AccountProvider.read",
            AsyncMock(return_value=(observed, {"uid": "invalid", "attributes": {}})),
        ),
        patch("identity.services.account_provider.AccountProvider.apply", mutation),
    ):
        result = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/review",
            headers={**signed(key), "Idempotency-Key": secrets.token_hex(10)},
            json={
                "action": "approve",
                "version": 1,
                "reason": "Independently verified identity",
                "attested": True,
            },
        )
    assert result.status_code == 202
    assert result.json()["history"][0]["status"] == "queued"
    mutation.assert_not_called()


async def test_pending_email_lookup_and_server_create_guard(review_app, client):
    _, key, _ = review_app
    observed = applicant(workspace_name="Requested Books", state_code="")
    with patch(
        "identity.services.account_provider.AccountProvider.pending_email",
        AsyncMock(side_effect=[[], [observed]]),
    ):
        lookup = await client.get(
            "/v1/platform/accounts/pending-registration",
            params={"email": observed.email},
            headers=signed(key),
        )
        assert lookup.status_code == 200 and lookup.json() == {"match": None}
        create = await client.post(
            "/v1/platform/tenants",
            headers={**signed(key), "Idempotency-Key": secrets.token_hex(10)},
            json={
                "name": "Duplicate Books",
                "administrator_name": observed.name,
                "administrator_email": observed.email,
                "country_code": "IN",
                "administrator_password": "temporary-secret-for-test",
                "recipient_confirmed": True,
            },
        )
        assert create.status_code == 409, create.text
    with patch(
        "identity.services.account_provider.AccountProvider.pending_email",
        AsyncMock(return_value=[observed]),
    ):
        lookup = await client.get(
            "/v1/platform/accounts/pending-registration",
            params={"email": observed.email},
            headers=signed(key),
        )
        assert lookup.status_code == 200
        assert lookup.json()["match"]["workspace_name"] == "Requested Books"


async def test_activated_subject_cannot_self_create_while_approval_is_queued(review_app, client):
    _, key, _ = review_app
    observed = applicant(workspace_name="North Books", state_code="")
    with patch(
        "identity.services.account_provider.AccountProvider.page",
        AsyncMock(return_value=([observed], False)),
    ):
        await client.post("/v1/platform/accounts/sync", headers=signed(key))
    row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]
    with patch(
        "identity.services.account_provider.AccountProvider.read",
        AsyncMock(side_effect=AccountProviderUnavailableError("offline")),
    ):
        decision = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/review",
            headers={**signed(key), "Idempotency-Key": secrets.token_hex(10)},
            json={
                "action": "approve",
                "version": 1,
                "reason": "Independently verified identity",
                "attested": True,
            },
        )
        assert decision.status_code == 202
        assert decision.json()["history"][0]["status"] == "queued"
    claims = bearer(
        key,
        subject=secrets.token_hex(32),
        email=observed.email,
        email_verified=True,
        auth_time=int(time.time()),
    )
    response = await client.post(
        "/v1/onboarding/tenant",
        headers=claims,
        json={
            "name": "A second workspace",
            "administrator_name": observed.name,
            "country_code": "IN",
        },
    )
    assert response.status_code == 409


async def test_outage_keeps_saved_intent_and_stale_review_is_denied(review_app, client):
    _, key, _ = review_app
    with patch(
        "identity.services.account_provider.AccountProvider.page",
        AsyncMock(return_value=([applicant()], False)),
    ):
        await client.post("/v1/platform/accounts/sync", headers=signed(key))
    row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]
    with patch(
        "identity.services.account_provider.AccountProvider.read",
        AsyncMock(side_effect=AccountProviderUnavailableError("offline")),
    ):
        result = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/review",
            headers={**signed(key), "Idempotency-Key": secrets.token_hex(10)},
            json={"action": "reject", "version": 1, "reason": "Not accepted"},
        )
        assert result.status_code == 202 and result.json()["status"] == "pending"
        assert result.json()["history"][0]["status"] == "queued"
    stale = await client.post(
        "/v1/platform/accounts/" + row["id"] + "/review",
        headers={**signed(key), "Idempotency-Key": secrets.token_hex(10)},
        json={"action": "approve", "version": 1, "reason": "Reviewed", "attested": True},
    )
    assert stale.status_code == 409


async def test_changed_email_blocks_provider_mutation_and_revoked_role_denies(
    review_app, client, factory
):
    _, key, tenant = review_app
    observed = applicant()
    with patch(
        "identity.services.account_provider.AccountProvider.page",
        AsyncMock(return_value=([observed], False)),
    ):
        await client.post("/v1/platform/accounts/sync", headers=signed(key))
    row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]
    changed = applicant(provider_uuid=observed.provider_uuid, email="changed@example.invalid")
    mutation = AsyncMock()
    with (
        patch(
            "identity.services.account_provider.AccountProvider.read",
            AsyncMock(return_value=(changed, {"attributes": {}})),
        ),
        patch("identity.services.account_provider.AccountProvider.apply", mutation),
    ):
        result = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/review",
            headers={**signed(key), "Idempotency-Key": secrets.token_hex(10)},
            json={
                "action": "approve",
                "version": 1,
                "reason": "Checked independently",
                "attested": True,
            },
        )
        assert result.status_code == 202
        assert (
            result.json()["needs_attention"] and result.json()["history"][0]["status"] == "blocked"
        )
        mutation.assert_not_called()
    from identity.models import RoleAssignment

    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            assignments = list(await db.scalars(select(RoleAssignment)))
            for assignment in assignments:
                assignment.is_active = False
    assert (await client.get("/v1/platform/accounts", headers=signed(key))).status_code == 403


async def test_changed_profile_requires_explicit_reconciliation(review_app, client):
    _, key, _ = review_app
    observed = applicant()
    with patch(
        "identity.services.account_provider.AccountProvider.page",
        AsyncMock(return_value=([observed], False)),
    ):
        await client.post("/v1/platform/accounts/sync", headers=signed(key))
    row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]
    changed = applicant(provider_uuid=observed.provider_uuid, email="new-address@example.invalid")
    mutation = AsyncMock()
    with (
        patch(
            "identity.services.account_provider.AccountProvider.read",
            AsyncMock(return_value=(changed, {"attributes": {}})),
        ),
        patch("identity.services.account_provider.AccountProvider.apply", mutation),
    ):
        response = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/review",
            headers={**signed(key), "Idempotency-Key": secrets.token_hex(10)},
            json={
                "action": "approve",
                "version": 1,
                "reason": "Independently checked",
                "attested": True,
            },
        )
        version = response.json()["version"]
        reconciled = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/reconcile",
            headers=signed(key),
            json={"version": version, "reason": "Rechecked changed contact information"},
        )
        assert reconciled.status_code == 200, reconciled.text
        assert reconciled.json()["email"] == changed.email
        assert not reconciled.json()["needs_attention"]
        assert (
            reconciled.json()["status"] == "pending" and not reconciled.json()["provider_verified"]
        )
        mutation.assert_not_called()
        stale = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/reconcile",
            headers=signed(key),
            json={"version": version, "reason": "Repeat old reconciliation"},
        )
        assert stale.status_code == 409


async def test_lost_native_write_response_is_reconciled_without_second_mutation(
    review_app, client, factory
):
    _, key, tenant = review_app
    observed = applicant()
    with patch(
        "identity.services.account_provider.AccountProvider.page",
        AsyncMock(return_value=([observed], False)),
    ):
        await client.post("/v1/platform/accounts/sync", headers=signed(key))
    row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]
    headers = {**signed(key), "Idempotency-Key": secrets.token_hex(10)}
    body = {
        "action": "approve",
        "version": 1,
        "reason": "Checked independent evidence",
        "attested": True,
    }
    mutation = AsyncMock(side_effect=AccountProviderUnavailableError("response lost"))
    with (
        patch(
            "identity.services.account_provider.AccountProvider.read",
            AsyncMock(return_value=(observed, {"attributes": {}})),
        ),
        patch("identity.services.account_provider.AccountProvider.apply", mutation),
    ):
        queued = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/review", headers=headers, json=body
        )
        assert queued.json()["history"][0]["status"] == "queued"
    approved = applicant(provider_uuid=observed.provider_uuid, is_active=True, verified=True)
    with tenant_scope(tenant):
        async with factory() as db:
            command = await db.scalar(select(AccountReviewCommand))
            tag = str(command.id)
    mutation = AsyncMock()
    with (
        patch(
            "identity.services.account_provider.AccountProvider.read",
            AsyncMock(
                return_value=(approved, {"attributes": {"billing_account_review_command": tag}})
            ),
        ),
        patch("identity.services.account_provider.AccountProvider.apply", mutation),
    ):
        replay = await client.post(
            "/v1/platform/accounts/" + row["id"] + "/review", headers=headers, json=body
        )
        assert replay.status_code == 202 and replay.json()["status"] == "approved"
        mutation.assert_not_called()


async def test_fresh_proof_validation_and_live_grants_bypass_stale_cache(
    review_app, client, factory
):
    app, key, tenant = review_app
    with patch(
        "identity.services.account_provider.AccountProvider.page",
        AsyncMock(return_value=([applicant()], False)),
    ):
        await client.post("/v1/platform/accounts/sync", headers=signed(key))
    row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]
    path = "/v1/platform/accounts/" + row["id"] + "/review"
    body = {"action": "approve", "version": 1, "reason": "Independent check", "attested": True}
    headers = {**signed(key), "Idempotency-Key": secrets.token_hex(10)}
    assert (
        await client.post(path, json={**body, "attested": False}, headers=headers)
    ).status_code == 422
    stale = bearer(
        key, email="admin@example.com", email_verified=True, auth_time=int(time.time()) - 600
    )
    response = await client.post(
        path, json=body, headers={**stale, "Idempotency-Key": secrets.token_hex(10)}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "platform_reauthentication_required"
    from identity.models import RoleAssignment, User
    from identity.services.login import live_grants

    with tenant_scope(tenant):
        async with factory() as db:
            user = await db.scalar(select(User))
            cached = await live_grants(db, user.id)
        async with factory() as db, db.begin():
            for assignment in await db.scalars(select(RoleAssignment)):
                assignment.is_active = False
    app.state.grant_cache = AsyncMock()
    app.state.grant_cache.resolve.return_value = cached
    mutation = AsyncMock()
    with patch("identity.services.account_provider.AccountProvider.apply", mutation):
        assert (await client.post(path, json=body, headers=headers)).status_code == 403
        assert (await client.get("/v1/platform/accounts", headers=signed(key))).status_code == 403
        mutation.assert_not_called()
    with tenant_scope(tenant):
        async with factory() as db:
            assert not list(await db.scalars(select(AccountReviewCommand)))


async def test_review_intent_and_audit_roll_back_together(review_app, client, factory):
    _, key, tenant = review_app
    observed = applicant()
    with patch(
        "identity.services.account_provider.AccountProvider.page",
        AsyncMock(return_value=([observed], False)),
    ):
        await client.post("/v1/platform/accounts/sync", headers=signed(key))
    row = (await client.get("/v1/platform/accounts", headers=signed(key))).json()["items"][0]
    from identity.api.auth import Actor
    from identity.models import AccountReview, User
    from identity.schemas.account_review import AccountDecision
    from identity.services.account_review import decide

    with tenant_scope(tenant):
        with pytest.raises(RuntimeError, match="rollback proof"):
            async with factory() as db, db.begin():
                user = await db.scalar(select(User))
                await decide(
                    db,
                    Actor(tenant, user.id),
                    uuid.UUID(row["id"]),
                    AccountDecision(action="reject", version=1, reason="Independent rejection"),
                    secrets.token_hex(10),
                )
                raise RuntimeError("rollback proof")
        async with factory() as db:
            assert not list(await db.scalars(select(AccountReviewCommand)))
            assert not list(
                await db.scalars(
                    select(Outbox).where(Outbox.event_type == "platform.account_decision_requested")
                )
            )
            assert (await db.get(AccountReview, uuid.UUID(row["id"]))).version == 1
