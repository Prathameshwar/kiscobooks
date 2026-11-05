"""Real MySQL migration, starter publication and concurrent retry verification."""

import asyncio
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.mysql


@pytest_asyncio.fixture
async def native_pricing_database(monkeypatch):
    configured = os.getenv("CATALOG_TEST_MYSQL_SERVER_URL")
    if not configured:
        pytest.skip("Set CATALOG_TEST_MYSQL_SERVER_URL to an isolated loopback MySQL server")
    server = make_url(configured)
    if server.database or server.host not in {"127.0.0.1", "localhost"} or server.port != 13398:
        raise ValueError("Pricing migration tests require the dedicated 13398 server")
    schema = "catalog_test_" + uuid.uuid4().hex
    admin = create_engine(server.render_as_string(hide_password=False))
    engine = None
    try:
        async with admin.begin() as db:
            await db.execute(text(f"CREATE DATABASE `{schema}`"))
        url = server.set(database=schema).render_as_string(hide_password=False)
        monkeypatch.setenv("CATALOG_DATABASE_URL", url)
        engine = create_engine(url)
        yield engine, Config(str(Path(__file__).resolve().parents[3] / "dbs/catalog/alembic.ini"))
    finally:
        if engine:
            await engine.dispose()
        async with admin.begin() as db:
            await db.execute(text(f"DROP DATABASE `{schema}`"))
        await admin.dispose()


async def test_legacy_pricing_survives_migration_and_authored_modes_block_rollback(
    native_pricing_database,
):
    engine, config = native_pricing_database
    async with engine.begin() as db:
        await db.execute(
            text(
                "CREATE TABLE product_pricing_policy "
                "(id INTEGER PRIMARY KEY, sale_level_count INTEGER NOT NULL)"
            )
        )
        await db.execute(text("INSERT INTO product_pricing_policy VALUES (1, 3)"))
    await asyncio.to_thread(command.stamp, config, "0215")
    await asyncio.to_thread(command.upgrade, config, "0216")
    async with engine.connect() as db:
        row = (await db.execute(text("SELECT * FROM product_pricing_policy"))).mappings().one()
        assert row["sale_level_count"] == 3
        assert all(value == "INHERIT" for key, value in row.items() if key.endswith("_mode"))
    await asyncio.to_thread(command.downgrade, config, "0215")
    await asyncio.to_thread(command.upgrade, config, "0216")
    async with engine.begin() as db:
        await db.execute(text("UPDATE product_pricing_policy SET unit_prices_mode = 'DISABLED'"))
    with pytest.raises(RuntimeError, match="cannot discard authored"):
        await asyncio.to_thread(command.downgrade, config, "0215")
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "0216"
        assert await db.scalar(text("SELECT sale_level_count FROM product_pricing_policy")) == 3


@pytest.mark.usefixtures("stable_product_source_clock")
async def test_native_starter_publication_and_concurrent_retry(native_pricing_database, tenant_a):
    from catalog.metadata import service_metadata
    from catalog.models.configuration import ProductConfigurationRevision
    from catalog.tasks.company_configuration_defaults import ensure_configuration_defaults
    from catalog.tasks.company_pricing_defaults import ensure_pricing_defaults
    from catalog.tasks.company_product_defaults import ensure_product_defaults
    from tests.test_unit_defaults import provision

    engine, config = native_pricing_database
    await asyncio.to_thread(command.upgrade, config, "head")
    await asyncio.to_thread(command.downgrade, config, "0215")
    await asyncio.to_thread(command.upgrade, config, "head")
    async with engine.connect() as db:
        assert (
            await db.run_sync(
                lambda connection: compare_metadata(
                    MigrationContext.configure(connection), service_metadata()
                )
            )
            == []
        )
    factory = create_session_factory(engine, guarded=True)
    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_product_defaults(db, company)
            await ensure_pricing_defaults(db, company)

        async def attempt():
            async with factory.begin() as db:
                return await ensure_configuration_defaults(db, company)

        results = await asyncio.gather(attempt(), attempt())
        assert all(result.status == "READY" for result in results)
        assert sorted(result.created_records > 0 for result in results) == [False, True]
        async with factory() as db:
            assert len(list(await db.scalars(select(ProductConfigurationRevision)))) == 1
    import httpx
    from pydantic import SecretStr

    from catalog.config import Settings
    from catalog.main import create_app
    from tests.conftest import ACTOR_SECRET
    from tests.test_company_configuration_defaults import (
        test_starter_is_effective_and_can_publish_a_later_change,
    )

    app = create_app(Settings(actor_signing_secret=SecretStr(ACTOR_SECRET)), engine=engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://catalog.test"
        ) as client:
            await test_starter_is_effective_and_can_publish_a_later_change(client, factory, uuid7())
