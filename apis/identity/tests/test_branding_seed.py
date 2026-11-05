"""Deployment branding changes preserve bootstrap proof, tenant data and audit atomicity."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, patch

import pytest
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from sqlalchemy import select

from identity.models import Outbox, PlatformInstallation, Tenant
from identity.seeds.branding import apply_branding_seed, seed_branding
from identity.seeds.installation import seed_installation
from tests.factories import build_country, build_currency, build_tenant


def test_cli_reads_private_file_without_requiring_provider_configuration(
    tmp_path, monkeypatch, capsys
):
    from identity.seeds.branding import BrandingSeedOutcome, main

    monkeypatch.delenv("IDENTITY_DATABASE_URL", raising=False)
    env = tmp_path / "identity.env"
    env.write_text(
        "IDENTITY_DATABASE_URL=sqlite+aiosqlite:///:memory:\n"
        "IDENTITY_LOCAL_AUTH=not-yet-configured\n",
        encoding="utf-8",
    )
    with patch("identity.seeds.branding.apply_branding_seed", new_callable=AsyncMock) as apply:
        apply.return_value = BrandingSeedOutcome(updated=1)
        assert main(["--env-file", str(env), "--dry-run"]) == 0
        apply.assert_awaited_once_with("sqlite+aiosqlite:///:memory:", dry_run=True)
    output = capsys.readouterr().out
    assert "KiscoBooks / Khushiyan Enterprise" in output
    assert "dry run: rolled back" in output
    assert "DATABASE_URL" not in output


def test_cli_failure_is_nonzero_and_keeps_exception_details_private(monkeypatch, capsys):
    from identity.seeds.branding import main

    monkeypatch.setenv("IDENTITY_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    with patch("identity.seeds.branding.apply_branding_seed", new_callable=AsyncMock) as apply:
        apply.side_effect = RuntimeError("private connection details")
        assert main([]) == 1
    assert "private connection details" not in capsys.readouterr().out


async def test_fresh_installation_uses_brand_default_and_stays_uncompleted(session):
    await seed_installation(session)
    row = await session.scalar(select(PlatformInstallation))
    assert row.name == "KiscoBooks"
    assert row.completed_at is None
    assert row.tenant_id is None
    await seed_installation(session)
    assert (await session.scalar(select(PlatformInstallation))).id == row.id


@pytest.mark.parametrize("name", ["JANSO", "Janso", " janso "])
async def test_completed_installation_rebrands_once_and_preserves_proof(session, tenant_a, name):
    session.add(build_currency())
    await session.flush()
    session.add(build_country())
    await session.flush()
    with tenant_scope(tenant_a):
        session.add(build_tenant(tenant_id=tenant_a))
        await session.flush()
    row = PlatformInstallation(
        id=uuid7(),
        key="platform",
        name=name,
        public_url="https://books.example.com",
        completed_at=utcnow(),
        tenant_id=tenant_a,
        administrator_id=uuid7(),
        administrator_subject="existing-provider-subject",
        request_hash="a" * 64,
    )
    session.add(row)
    await session.flush()
    protected = tuple(
        getattr(row, key)
        for key in (
            "id",
            "key",
            "public_url",
            "completed_at",
            "tenant_id",
            "administrator_id",
            "administrator_subject",
            "request_hash",
        )
    )
    with tenant_scope(tenant_a):
        before_tenant = (await session.get(Tenant, tenant_a)).name
    result = await seed_branding(session)
    assert result.updated == 1
    assert row.name == "KiscoBooks"
    assert (
        tuple(
            getattr(row, key)
            for key in (
                "id",
                "key",
                "public_url",
                "completed_at",
                "tenant_id",
                "administrator_id",
                "administrator_subject",
                "request_hash",
            )
        )
        == protected
    )
    with tenant_scope(tenant_a):
        assert (await session.get(Tenant, tenant_a)).name == before_tenant
    assert (await seed_branding(session)).updated == 0
    with tenant_scope(tenant_a):
        events = list(await session.scalars(select(Outbox)))
        assert len(events) == 1
        assert events[0].event_type == "platform.details_updated"
        assert events[0].payload["actor_type"] == "system"
        assert events[0].payload["actor_user_id"] is None
        assert events[0].payload["source_service"] == "identity"
        assert events[0].payload["changes"] == {"name": {"changed": True}}


@pytest.mark.parametrize("name", ["KiscoBooks", "Custom Books", "JANSO Retail", None, ""])
async def test_completed_custom_or_unknown_name_is_preserved(session, tenant_a, name):
    session.add(
        PlatformInstallation(key="platform", name=name, completed_at=utcnow(), tenant_id=tenant_a)
    )
    await session.flush()
    assert (await seed_branding(session)).updated == 0
    assert (await session.scalar(select(PlatformInstallation))).name == name


@pytest.mark.parametrize("name", [None, "", "  ", "JANSO"])
async def test_uncompleted_defaults_sync_without_creating_operator_or_completion(session, name):
    row = PlatformInstallation(key="platform", name=name)
    session.add(row)
    await session.flush()
    assert (await seed_branding(session)).updated == 1
    assert row.name == "KiscoBooks"
    assert row.completed_at is None and row.administrator_id is None and row.tenant_id is None


async def test_seed_refuses_missing_control_record(session):
    with pytest.raises(ValueError, match="installation"):
        await seed_branding(session)


async def test_seed_refuses_completed_control_record_without_tenant(session):
    session.add(PlatformInstallation(key="platform", name="JANSO", completed_at=utcnow()))
    await session.flush()
    with pytest.raises(ValueError, match="tenant"):
        await seed_branding(session)
    assert (await session.scalar(select(PlatformInstallation))).name == "JANSO"


async def test_dry_run_and_audit_failure_roll_back_all_changes(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'branding.db'}"
    engine = create_engine(url)
    from billing_platform.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    identifier = uuid7()
    tenant = uuid7()
    try:
        async with factory() as session, session.begin():
            session.add(
                PlatformInstallation(
                    id=identifier,
                    key="platform",
                    name="JANSO",
                    completed_at=dt.datetime(2026, 10, 30, tzinfo=dt.UTC),
                    tenant_id=tenant,
                )
            )
        assert (await apply_branding_seed(url, dry_run=True)).updated == 1
        async with factory() as session:
            assert (await session.get(PlatformInstallation, identifier)).name == "JANSO"
            with tenant_scope(tenant):
                assert (await session.scalars(select(Outbox))).all() == []
        with patch("identity.seeds.branding.emit", side_effect=RuntimeError("audit unavailable")):
            with pytest.raises(RuntimeError):
                await apply_branding_seed(url)
        async with factory() as session:
            assert (await session.get(PlatformInstallation, identifier)).name == "JANSO"
        assert (await apply_branding_seed(url)).updated == 1
        assert (await apply_branding_seed(url)).updated == 0
        async with factory() as session:
            assert (await session.get(PlatformInstallation, identifier)).name == "KiscoBooks"
            with tenant_scope(tenant):
                assert len((await session.scalars(select(Outbox))).all()) == 1
    finally:
        await engine.dispose()
