from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest
from billing_platform.constants import SCOPE_ALL
from billing_platform.db import unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError
from billing_platform.outbox import emit
from sqlalchemy import func, select

from identity.domain.system_roles import get
from identity.models import Role, RolePermission
from identity.seeds import business_classifications, roles
from identity.tasks import audit_outbox
from tests.factories import build_role, build_role_permission
from tests.test_gap_audit import settings


async def test_role_deployment_dry_run_restore_and_withdrawal(engine, factory, monkeypatch):
    monkeypatch.setattr(roles, "create_engine", lambda _: engine)
    dispose = AsyncMock()
    monkeypatch.setattr(type(engine), "dispose", dispose)
    outcomes = await roles.apply_role_seed("unused", dry_run=True)
    assert outcomes[0].changed and "inserted=" in str(outcomes[0])
    async with factory() as db:
        with unfiltered():
            assert await db.scalar(select(func.count(Role.id))) == 0
    await roles.apply_role_seed("unused")
    async with factory() as db, db.begin():
        with unfiltered():
            row = await db.scalar(select(Role).where(Role.key == "billing_clerk"))
            row.is_active = False
            row.deactivated_at = utcnow()
            obsolete = build_role(tenant_id=SCOPE_ALL, key="withdrawn_test_role")
            db.add(obsolete)
            await db.flush()
            extra = next(
                p
                for p in {"company.create", "company.read", "user.update", "audit.read"}
                if p not in get("billing_clerk").permissions
            )
            db.add(build_role_permission(tenant_id=SCOPE_ALL, role_id=row.id, permission_key=extra))
    result = await roles.apply_role_seed("unused")
    assert result[0].updated == result[0].deactivated == result[1].revoked == 1
    async with factory() as db:
        with unfiltered():
            row = await db.scalar(select(Role).where(Role.key == "billing_clerk"))
            assert row.is_active and row.deactivated_at is None
            assert not (
                await db.scalar(select(Role).where(Role.key == "withdrawn_test_role"))
            ).is_active
            assert (
                await db.scalar(
                    select(RolePermission.id).where(
                        RolePermission.role_id == row.id, RolePermission.permission_key == extra
                    )
                )
                is None
            )
    assert dispose.await_count == 3


def test_role_cli_reports_dry_run(monkeypatch, capsys):
    apply = AsyncMock(return_value=[roles.RoleSeedOutcome("role", inserted=1)])
    monkeypatch.setattr(roles, "apply_role_seed", apply)
    monkeypatch.setattr(roles, "database_url", lambda _: "sqlite-test")
    assert roles.main(["--dry-run"]) == 0
    apply.assert_awaited_once_with("sqlite-test", dry_run=True)
    assert "dry run: rolled back" in capsys.readouterr().out
    assert roles.main([]) == 0


def test_business_seed_cli_requires_configuration_and_passes_dry_run(monkeypatch):
    monkeypatch.setattr("sys.argv", ["seed", "--dry-run"])
    monkeypatch.delenv("IDENTITY_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as error:
        business_classifications.main()
    assert error.value.code == 2
    monkeypatch.setenv("IDENTITY_DATABASE_URL", "sqlite-test")
    apply = AsyncMock()
    monkeypatch.setattr(business_classifications, "apply_seed", apply)
    assert business_classifications.main() == 0
    apply.assert_awaited_once_with("sqlite-test", dry_run=True)


async def test_outbox_operator_rejects_ineligible_retry_and_disposes(
    engine, factory, tenant_a, monkeypatch, capsys
):
    config = settings()
    monkeypatch.setattr(audit_outbox, "PublisherSettings", lambda: config)
    monkeypatch.setattr(audit_outbox, "create_engine", lambda _: engine)
    dispose = AsyncMock()
    monkeypatch.setattr(type(engine), "dispose", dispose)
    async with factory() as db, db.begin():
        row = emit(
            db,
            tenant_id=tenant_a,
            aggregate_id=uuid.uuid4(),
            aggregate_type="user",
            event_type="user.updated",
            payload={"private": "do not print"},
        )
        await db.flush()
        message = row.message_id
        with pytest.raises(NotFoundError):
            await audit_outbox.retry_event(db, config, uuid.uuid4())
        with pytest.raises(ConflictError, match="already eligible"):
            await audit_outbox.retry_event(db, config, message)
        row.published_at = utcnow()
        with pytest.raises(ConflictError, match="published"):
            await audit_outbox.retry_event(db, config, message)
        row.published_at = None
        row.attempt_count = config.maximum_attempts
    await audit_outbox.main(None)
    result = json.loads(capsys.readouterr().out)
    assert result["exhausted"] == 1 and "private" not in str(result)
    await audit_outbox.main(message)
    assert json.loads(capsys.readouterr().out)["exhausted"] == 0
    with pytest.raises(ConflictError):
        await audit_outbox.main(message)
    assert dispose.await_count == 3


async def test_support_worker_disposes_on_cancellation_and_rejects_unbounded_batches(
    engine, factory, app, monkeypatch
):
    import asyncio

    from identity.api.auth import Actor
    from identity.tasks import bank_encryption, support_expiry

    for limit in (0, 101):
        with pytest.raises(ValueError, match="expiry batch"):
            await support_expiry.expire_batch(factory, limit)
        with pytest.raises(ValueError, match="bank batch"):
            await bank_encryption.rotate_batch(
                None,
                Actor(uuid.uuid4(), uuid.uuid4()),
                app.state.settings,
                uuid.uuid4(),
                limit=limit,
            )
    monkeypatch.setattr(support_expiry, "create_engine", lambda _: engine)
    dispose = AsyncMock()
    monkeypatch.setattr(type(engine), "dispose", dispose)
    sleep = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(support_expiry.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await support_expiry.run(app.state.settings)
    sleep.assert_awaited_once_with(30)
    dispose.assert_awaited_once()
