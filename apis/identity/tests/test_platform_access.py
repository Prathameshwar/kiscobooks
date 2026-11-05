from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import select

from identity.domain.system_roles import SYSTEM_ROLES
from identity.models import Outbox, RoleAssignment, User
from tests.factories import build_user
from tests.test_gap_login import bearer
from tests.test_platform_details import complete
from tests.test_platform_setup import signed

pytest_plugins = ["tests.test_platform_setup"]


def test_platform_administrator_has_explicit_bounded_access():
    roles = {role.key: role.permissions for role in SYSTEM_ROLES}
    assert {"platform.tenant_access.read", "platform.tenant_access.manage"} <= roles[
        "platform_admin"
    ]
    assert "role.assign" not in roles["platform_admin"]
    assert "user.update" not in roles["platform_admin"]
    assert "platform.tenant_access.read" not in roles["tenant_auditor"]


async def test_platform_can_review_fixed_administrator_role(client, setup_app):
    key, _ = await complete(client, setup_app)
    response = await client.get("/v1/platform/access/role", headers=signed(key))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["key"] == "tenant_admin"
    assert body["is_system"] is True
    assert "user.invite" in body["permissions"]
    assert not any(permission.startswith("platform.") for permission in body["permissions"])


@pytest.fixture
async def access_tenant(client, setup_app):
    key, platform = await complete(client, setup_app)
    setup_app[0].state.settings.public_auth_url = "http://localhost:4310"
    response = await client.post(
        "/v1/platform/tenants",
        headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
        json={
            "name": "Customer Workspace",
            "country_code": "IN",
            "currency_code": "INR",
            "administrator_email": "owner@example.com",
            "administrator_name": "Owner",
            "administrator_password": "temporary-secret-for-test",
            "recipient_confirmed": True,
        },
    )
    assert response.status_code == 201, response.text
    tenant = response.json()["id"]
    response = await client.get(
        f"/v1/platform/access/tenants/{tenant}/administrators", headers=signed(key)
    )
    assert response.status_code == 200, response.text
    owner = response.json()["items"][0]["id"]
    return key, platform, tenant, owner


async def admin_detail(client, key, tenant, owner):
    response = await client.get(
        f"/v1/platform/access/tenants/{tenant}/administrators/{owner}", headers=signed(key)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_new_tenant_administrator_assignment_inherits_opening_authority(
    access_tenant, factory
):
    from billing_platform.db import unfiltered

    from identity.models import RolePermission
    from tests.test_tenant_admin_opening_authority import OPENING

    _, _, tenant, owner = access_tenant
    async with factory() as db:
        with tenant_scope(uuid.UUID(tenant)):
            assignment = await db.scalar(
                select(RoleAssignment).where(RoleAssignment.subject_id == uuid.UUID(owner))
            )
        with unfiltered():
            permissions = set(
                await db.scalars(
                    select(RolePermission.permission_key).where(
                        RolePermission.role_id == assignment.role_id
                    )
                )
            )
    assert OPENING <= permissions


def change_body(detail, action="edit", **extra):
    return {
        "action": action,
        "expected_updated_at": detail["updated_at"],
        "expected_assignment_updated_at": detail["assignment_updated_at"],
        "reason": "Administrator access review",
        **extra,
    }


async def test_administrator_roster_is_bounded_and_wrong_tenant_denied(
    client, access_tenant, factory
):
    key, platform, tenant, owner = access_tenant
    with tenant_scope(uuid.UUID(tenant)):
        async with factory() as db, db.begin():
            ordinary = build_user(tenant_id=uuid.UUID(tenant), email="ordinary@example.com")
            db.add(ordinary)
            ordinary_id = ordinary.id
    response = await client.get(
        f"/v1/platform/access/tenants/{tenant}/administrators", headers=signed(key)
    )
    assert [row["id"] for row in response.json()["items"]] == [owner]
    assert (
        await client.get(
            f"/v1/platform/access/tenants/{tenant}/administrators/{ordinary_id}",
            headers=signed(key),
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/v1/platform/access/tenants/{platform['tenant_id']}/administrators/{owner}",
            headers=signed(key),
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/v1/platform/access/tenants/{uuid.uuid4()}/administrators/{owner}",
            headers=signed(key),
        )
    ).status_code == 404
    choices = (await client.get("/v1/platform/access/tenants", headers=signed(key))).json()
    assert tenant in [row["id"] for row in choices["items"]]
    assert platform["tenant_id"] not in [row["id"] for row in choices["items"]]
    assert set(choices["items"][0]) == {"id", "name", "status"}


async def test_invitation_exact_replay_and_changed_body_conflict(client, access_tenant, factory):
    key, _, tenant, _ = access_tenant
    path = f"/v1/platform/access/tenants/{tenant}/administrators"
    headers = {**signed(key), "Idempotency-Key": str(uuid.uuid4())}
    body = {
        "display_name": "Second Administrator",
        "email": "second@example.com",
        "reason": "Provide backup administrator",
    }
    first = await client.post(path, headers=headers, json=body)
    assert first.status_code == 201, first.text
    receipt = first.json()
    assert receipt["status"] == "invited" and receipt["assignment_active"]
    assert receipt["invitation_url"].startswith("http://localhost:4310/accept?")
    replay = await client.post(path, headers=headers, json=body)
    assert replay.json() == receipt
    assert (
        await client.post(path, headers=headers, json={**body, "display_name": "Different"})
    ).status_code == 422
    with tenant_scope(uuid.UUID(tenant)):
        async with factory() as db:
            users = list(await db.scalars(select(User).where(User.email == body["email"])))
            assert len(users) == 1
            assignment = await db.scalar(
                select(RoleAssignment).where(RoleAssignment.subject_id == users[0].id)
            )
            assert assignment.scope_type == "tenant"
            assert (
                len(
                    list(
                        await db.scalars(
                            select(Outbox).where(
                                Outbox.event_type == "role_assignment.granted",
                                Outbox.aggregate_id == assignment.id,
                            )
                        )
                    )
                )
                == 1
            )


async def test_edit_replay_staleness_and_audit_rollback(client, access_tenant, factory):
    key, _, tenant, owner = access_tenant
    detail = await admin_detail(client, key, tenant, owner)
    path = f"/v1/platform/access/tenants/{tenant}/administrators/{owner}/commands"
    body = change_body(detail, display_name="Updated Owner")
    proof = {**signed(key), "Idempotency-Key": str(uuid.uuid4())}
    first = await client.post(path, headers=proof, json=body)
    assert first.status_code == 200, first.text
    assert (await client.post(path, headers=proof, json=body)).json() == first.json()
    assert (
        await client.post(
            path, headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())}, json=body
        )
    ).status_code == 409
    updated = await admin_detail(client, key, tenant, owner)
    assert updated["display_name"] == "Updated Owner"
    with patch(
        "identity.services.platform_access.record", side_effect=RuntimeError("audit unavailable")
    ):
        failed = await client.post(
            path,
            headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
            json=change_body(updated, display_name="Must roll back"),
        )
        assert failed.status_code == 500
    assert (await admin_detail(client, key, tenant, owner))["display_name"] == "Updated Owner"


async def test_last_active_administrator_and_lifecycle(client, access_tenant, factory):
    key, _, tenant, owner = access_tenant
    with tenant_scope(uuid.UUID(tenant)):
        async with factory() as db, db.begin():
            (await db.get(User, uuid.UUID(owner))).status = "active"
    detail = await admin_detail(client, key, tenant, owner)
    assert detail["last_active_administrator"] is True
    path = f"/v1/platform/access/tenants/{tenant}/administrators/{owner}/commands"
    for action in ["suspend", "revoke"]:
        response = await client.post(
            path,
            headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
            json=change_body(detail, action),
        )
        assert response.status_code == 409, response.text
    second = await client.post(
        f"/v1/platform/access/tenants/{tenant}/administrators",
        headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
        json={
            "display_name": "Backup",
            "email": "backup@example.com",
            "reason": "Provide another administrator",
        },
    )
    assert second.status_code == 201, second.text
    with tenant_scope(uuid.UUID(tenant)):
        async with factory() as db, db.begin():
            (await db.get(User, uuid.UUID(second.json()["administrator_id"]))).status = "active"
    for action, status, active in [
        ("suspend", "suspended", True),
        ("restore", "active", True),
        ("revoke", "active", False),
        ("restore", "active", True),
    ]:
        detail = await admin_detail(client, key, tenant, owner)
        response = await client.post(
            path,
            headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
            json=change_body(detail, action),
        )
        assert response.status_code == 200, response.text
        assert (
            response.json()["status"] == status and response.json()["assignment_active"] == active
        )


async def test_permissions_refresh_reauthentication_and_replay_revocation(
    client, access_tenant, factory
):
    key, platform, tenant, owner = access_tenant
    detail = await admin_detail(client, key, tenant, owner)
    path = f"/v1/platform/access/tenants/{tenant}/administrators/{owner}/commands"
    body = change_body(detail, display_name="Reviewed")
    stale = bearer(
        key, email="admin@example.com", email_verified=True, auth_time=int(time.time()) - 900
    )
    response = await client.post(
        path, headers={**stale, "Idempotency-Key": str(uuid.uuid4())}, json=body
    )
    assert (
        response.status_code == 403
        and response.json()["error"]["code"] == "platform_reauthentication_required"
    )
    assert (await client.get("/v1/platform/access/role")).status_code == 401
    proof = {**signed(key), "Idempotency-Key": str(uuid.uuid4())}
    assert (await client.post(path, headers=proof, json=body)).status_code == 200
    with tenant_scope(uuid.UUID(platform["tenant_id"])):
        async with factory() as db, db.begin():
            (await db.scalar(select(RoleAssignment))).is_active = False
    assert (await client.post(path, headers=proof, json=body)).status_code == 403
    assert (await client.get("/v1/platform/access/role", headers=signed(key))).status_code == 403


@pytest.mark.parametrize(
    "extra",
    [
        {"role_id": str(uuid.uuid4())},
        {"scope_type": "company"},
        {"user_type": "platform_admin"},
        {"display_name": " \n "},
        {"reason": " "},
        {"reason": " a "},
        {"display_name": 123},
        {"email": "bad space@example.com"},
        {"email": "one@two@example.com"},
    ],
)
async def test_invite_rejects_escalation_and_invalid_input(client, access_tenant, extra):
    key, _, tenant, _ = access_tenant
    response = await client.post(
        f"/v1/platform/access/tenants/{tenant}/administrators",
        headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
        json={
            "display_name": "New Administrator",
            "email": "new@example.com",
            "reason": "Approved invitation",
            **extra,
        },
    )
    assert response.status_code == 422, response.text


async def test_pending_invitation_resend_revoke_and_restore_are_auditable(
    client, access_tenant, factory
):
    from identity.events.audit_contract import AUDIT_EVENT_TYPES
    from identity.models import UserInvitation

    key, platform, tenant, _ = access_tenant
    invited = await client.post(
        f"/v1/platform/access/tenants/{tenant}/administrators",
        headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
        json={
            "display_name": "Invited Administrator",
            "email": "invited@example.com",
            "reason": "Invitation lifecycle test",
        },
    )
    assert invited.status_code == 201, invited.text
    owner = invited.json()["administrator_id"]
    path = f"/v1/platform/access/tenants/{tenant}/administrators/{owner}/commands"
    for action in ["resend_invitation", "revoke", "restore", "resend_invitation"]:
        detail = await admin_detail(client, key, tenant, owner)
        response = await client.post(
            path,
            headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
            json=change_body(detail, action),
        )
        assert response.status_code == 200, response.text
        if action == "resend_invitation":
            assert response.json()["invitation_url"]
    with tenant_scope(uuid.UUID(tenant)):
        async with factory() as db:
            invitations = list(
                await db.scalars(
                    select(UserInvitation).where(UserInvitation.user_id == uuid.UUID(owner))
                )
            )
            assert sum(row.status == "pending" for row in invitations) == 1
            events = list(await db.scalars(select(Outbox)))
            assert all(
                event.event_type in AUDIT_EVENT_TYPES
                for event in events
                if event.event_type.startswith(("user.", "role_assignment."))
            )
    with tenant_scope(uuid.UUID(platform["tenant_id"])):
        async with factory() as db:
            events = list(
                await db.scalars(
                    select(Outbox).where(
                        Outbox.event_type.startswith("platform.tenant_administrator")
                    )
                )
            )
            assert events and all(event.event_type in AUDIT_EVENT_TYPES for event in events)
            assert all("@" not in str(event.payload) for event in events)
            changed = next(
                event
                for event in events
                if event.event_type == "platform.tenant_administrator_resend_invitation"
            )
            assert changed.payload["changes"]["administrator_id"] == owner


async def test_closed_tenant_and_existing_user_cannot_receive_administrator_invitation(
    client, access_tenant, factory
):
    from identity.models import Tenant

    key, _, tenant, _ = access_tenant
    path = f"/v1/platform/access/tenants/{tenant}/administrators"
    body = {
        "display_name": "Duplicate",
        "email": "owner@example.com",
        "reason": "Review duplicate account",
    }
    response = await client.post(
        path, headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())}, json=body
    )
    assert response.status_code == 409
    with tenant_scope(uuid.UUID(tenant)):
        async with factory() as db, db.begin():
            (await db.get(Tenant, uuid.UUID(tenant))).status = "closed"
    assert (await client.get(path, headers=signed(key))).status_code == 200
    response = await client.post(
        path,
        headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
        json={**body, "email": "new@example.com"},
    )
    assert response.status_code == 409


async def test_company_scoped_platform_permission_cannot_reach_tenant_access(
    client, access_tenant, factory
):
    key, platform, tenant, _ = access_tenant
    with tenant_scope(uuid.UUID(platform["tenant_id"])):
        async with factory() as db, db.begin():
            assignment = await db.scalar(select(RoleAssignment))
            assignment.scope_type = "company"
            assignment.scope_id = uuid.uuid4()
    assert (await client.get("/v1/platform/access/role", headers=signed(key))).status_code == 403
    assert (
        await client.get(
            f"/v1/platform/access/tenants/{tenant}/administrators", headers=signed(key)
        )
    ).status_code == 403
