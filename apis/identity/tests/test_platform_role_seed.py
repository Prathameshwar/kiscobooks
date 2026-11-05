"""Permanent report capability and reviewed system-role reconciliation boundaries."""

import uuid

import pytest
from billing_platform.constants import SCOPE_ALL
from billing_platform.db import tenant_scope, unfiltered
from sqlalchemy import delete, select

from identity.domain.system_roles import get
from identity.models import Outbox, Role, RolePermission
from tests.test_gap_login import bearer
from tests.test_platform_details import complete
from tests.test_platform_setup import signed

pytest_plugins = ["tests.test_platform_setup"]
BASE = "/v1/platform/system-roles"


def test_tenant_admin_has_complete_reporting_without_voucher_or_closing_authority():
    permissions = get("tenant_admin").permissions
    assert {
        "report.read",
        "report.export",
        "report.definition.manage",
        "ledger.read",
        "accounting.head.read",
        "accounting.group.read",
        "accounting.account.read",
        "accounting.party.read",
        "accounting.setup.read",
        "accounting.finance.read",
        "period.read",
    } <= permissions
    assert (
        not {
            "vouchers.post",
            "vouchers.approve",
            "period.close",
            "period.reopen",
            "user.impersonate",
            "audit.read_security",
        }
        & permissions
    )


async def test_review_apply_and_replay_preserve_ids_and_custom_roles(client, setup_app, factory):
    key, platform = await complete(client, setup_app)
    async with factory() as db, db.begin():
        with unfiltered():
            admin = await db.scalar(
                select(Role).where(Role.tenant_id == SCOPE_ALL, Role.key == "tenant_admin")
            )
            retained_id = admin.id
            await db.execute(
                delete(RolePermission).where(
                    RolePermission.role_id == admin.id,
                    RolePermission.permission_key == "report.export",
                )
            )
            custom = Role(
                id=uuid.uuid4(),
                tenant_id=uuid.UUID(platform["tenant_id"]),
                key="custom_reader",
                name="Custom reader",
            )
            db.add(custom)
            custom_id = custom.id
    preview = await client.get(BASE, headers=signed(key))
    assert preview.status_code == 200, preview.text
    plan = preview.json()
    assert any(
        row["key"] == "tenant_admin" and "report.export" in row["added"] for row in plan["changes"]
    )
    body = {
        "expected_current_digest": plan["current_digest"],
        "expected_catalogue_digest": plan["catalogue_digest"],
        "reason": "Apply reviewed permanent reporting authority",
    }
    headers = {**signed(key), "Idempotency-Key": str(uuid.uuid4())}
    applied = await client.post(BASE + "/reconcile", headers=headers, json=body)
    assert applied.status_code == 200, applied.text
    assert applied.json()["changed"]
    replay = await client.post(BASE + "/reconcile", headers=headers, json=body)
    assert replay.status_code == 200 and replay.json() == applied.json()
    async with factory() as db:
        with unfiltered():
            admin = await db.scalar(
                select(Role).where(Role.tenant_id == SCOPE_ALL, Role.key == "tenant_admin")
            )
            assert admin.id == retained_id
            assert await db.get(Role, custom_id) is not None
            permissions = set(
                await db.scalars(
                    select(RolePermission.permission_key).where(RolePermission.role_id == admin.id)
                )
            )
            assert permissions == get("tenant_admin").permissions
    with tenant_scope(uuid.UUID(platform["tenant_id"])):
        async with factory() as db:
            events = list(
                await db.scalars(
                    select(Outbox).where(Outbox.event_type == "platform.system_roles_reconciled")
                )
            )
            assert len(events) == 1
            assert events[0].payload["changes"]["catalogue_digest"] == plan["catalogue_digest"]
            assert events[0].payload["changes"]["added_grants"] == 1


@pytest.mark.parametrize("field", ["expected_current_digest", "expected_catalogue_digest"])
async def test_stale_preview_is_refused(client, setup_app, factory, field):
    key, _ = await complete(client, setup_app)
    plan = (await client.get(BASE, headers=signed(key))).json()
    body = {
        "expected_current_digest": plan["current_digest"],
        "expected_catalogue_digest": plan["catalogue_digest"],
        "reason": "Reviewed seed",
    }
    body[field] = "0" * 64
    response = await client.post(
        BASE + "/reconcile",
        headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
        json=body,
    )
    assert response.status_code == 409


async def test_only_fresh_configured_operator_can_apply(client, setup_app):
    key, _ = await complete(client, setup_app)
    assert (await client.get(BASE)).status_code == 401
    assert (await client.get(BASE, headers=signed(key, subject="foreign"))).status_code in {
        401,
        403,
    }
    plan = (await client.get(BASE, headers=signed(key))).json()
    body = {
        "expected_current_digest": plan["current_digest"],
        "expected_catalogue_digest": plan["catalogue_digest"],
        "reason": "Reviewed seed",
    }
    import time

    headers = {
        **bearer(
            key, email="admin@example.com", email_verified=True, auth_time=int(time.time()) - 600
        ),
        "Idempotency-Key": str(uuid.uuid4()),
    }
    assert (await client.post(BASE + "/reconcile", headers=headers, json=body)).status_code == 403
    body["permissions"] = ["ledger.post_journal"]
    assert (
        await client.post(
            BASE + "/reconcile",
            headers={**signed(key), "Idempotency-Key": str(uuid.uuid4())},
            json=body,
        )
    ).status_code == 422
