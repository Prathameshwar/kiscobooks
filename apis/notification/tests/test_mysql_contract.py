"""Real migrations and ownership constraints; never run against an application schema."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from notification.metadata import TABLES
from notification.models import ProviderAccount, SenderIdentity
from notification.ownership import session_factory

pytestmark = pytest.mark.mysql


@pytest.mark.asyncio
async def test_mysql_migration_roundtrip_and_cross_space_fk(mysql_url: str) -> None:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "dbs/notification/alembic.ini"))
    config.set_main_option("script_location", str(root / "dbs/notification"))
    config.attributes["database_url"] = mysql_url
    await asyncio.to_thread(command.upgrade, config, "0026")
    engine = create_async_engine(mysql_url)
    tenant, platform, provider = uuid7(), uuid7(), uuid7()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO provider_account (id,tenant_id,`key`,callback_key,channel,"
                    "provider_key,display_name,credential_ref,status,created_at,updated_at) "
                    "VALUES (:id,:tenant,'legacy',:callback,'email','ses','Legacy','registered',"
                    "'pending',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))"
                ),
                {"id": uuid7().bytes, "tenant": tenant.bytes, "callback": "l" * 43},
            )
        await asyncio.to_thread(command.upgrade, config, "0051")
        # Backfill downgrade deliberately retains data; replay must be restartable.
        await asyncio.to_thread(command.downgrade, config, "0050")
        await asyncio.to_thread(command.upgrade, config, "head")
        async with engine.connect() as conn:
            ownership = (
                await conn.execute(
                    text("SELECT space_id FROM provider_account WHERE `key`='legacy'")
                )
            ).scalar_one()
            assert ownership == tenant.bytes
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
            assert TABLES <= tables
            from notification.metadata import service_metadata

            for name, expected in service_metadata().tables.items():
                actual = await conn.run_sync(lambda c, name=name: inspect(c).get_columns(name))
                assert {column["name"] for column in actual} == set(expected.columns.keys()), name
                assert {column["name"]: column["nullable"] for column in actual} == {
                    column.name: column.nullable for column in expected.columns
                }, name
        factory = session_factory(engine)
        async with factory() as db:
            with unfiltered():
                db.add(
                    ProviderAccount(
                        id=provider,
                        tenant_id=tenant,
                        space_id=platform,
                        key="platform",
                        callback_key="m" * 43,
                        channel="email",
                        provider_key="ses",
                        display_name="Platform",
                        credential_ref="registered",
                        status="pending",
                    )
                )
                await db.commit()
        async with factory() as db:
            with tenant_scope(tenant):
                assert await db.get(ProviderAccount, provider) is None
                db.add(
                    SenderIdentity(
                        tenant_id=tenant,
                        provider_account_id=provider,
                        key="bad",
                        sender_type="email",
                        external_sender_id="sender@example.invalid",
                        display_name="Bad reference",
                        verification_status="unverified",
                    )
                )
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
        from tests.test_all_space_tables import test_every_owned_table_enforces_tenant_and_space

        await test_every_owned_table_enforces_tenant_and_space(engine)
        # Data is isolated and the FK rejects a wrong-space link even in trusted SQL.
        async with engine.begin() as conn:
            from notification.metadata import service_metadata

            for table in reversed(service_metadata().sorted_tables):
                await conn.execute(table.delete())
        await asyncio.to_thread(command.downgrade, config, "base")
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
            assert tables == {"alembic_version"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_mysql_concurrent_version_allocation_and_activation(mysql_url: str) -> None:
    import datetime as dt

    import httpx
    from pydantic import SecretStr

    from notification.config import Settings
    from notification.main import create_app
    from tests.api_support import ACTOR_SECRET, actor_headers

    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "dbs/notification/alembic.ini"))
    config.set_main_option("script_location", str(root / "dbs/notification"))
    config.attributes["database_url"] = mysql_url
    await asyncio.to_thread(command.upgrade, config, "head")
    app = create_app(
        Settings(
            database_url=mysql_url,
            actor_signing_secret=SecretStr(ACTOR_SECRET),
            cursor_signing_secret=SecretStr("c" * 32),
            data_encryption_key=SecretStr("d" * 32),
        )
    )
    proof = actor_headers(
        tenant_id=uuid7(), user_id=uuid7(), permissions=["notification.template.manage"]
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            template = await client.post(
                "/v1/templates",
                headers=proof,
                json={
                    "company_id": str(uuid7()),
                    "key": "concurrent",
                    "event_key": "voucher.shared",
                    "category": "transactional",
                    "default_locale": "en",
                },
            )
            assert template.status_code == 201
            variant = await client.post(
                f"/v1/templates/{template.json()['id']}/variants",
                headers=proof,
                json={"channel": "email", "locale": "en"},
            )
            path = f"/v1/variants/{variant.json()['id']}"
            versions = await asyncio.gather(
                *(
                    client.post(path + "/versions", headers=proof, json={"body_text": text})
                    for text in ("First version", "Second version")
                )
            )
            assert [r.status_code for r in versions] == [201, 201]
            assert sorted(r.json()["version"] for r in versions) == [1, 2]
            moment = (dt.datetime.now(dt.UTC) + dt.timedelta(seconds=5)).isoformat()
            activations = await asyncio.gather(
                *(
                    client.post(
                        path + "/activations",
                        headers=proof,
                        json={"template_version_id": version.json()["id"], "valid_from": moment},
                    )
                    for version in versions
                )
            )
            assert sorted(r.status_code for r in activations) == [201, 409]
    finally:
        await app.state.engine.dispose()
