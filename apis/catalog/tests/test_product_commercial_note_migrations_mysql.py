"""Native DDL and row preservation on a dedicated disposable test database."""

import asyncio
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from billing_platform.db import create_engine
from sqlalchemy import Column, Integer, MetaData, Numeric, String, Table, inspect, select, text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.mysql
ROOT = Path(__file__).resolve().parents[3]
TABLES = ("catalog_tax_binding", "item_price_draft", "item_price")


@pytest_asyncio.fixture
async def native_note_database(monkeypatch):
    configured = os.getenv("QA_MYSQL_SERVER_URL")
    if not configured:
        pytest.skip("Set QA_MYSQL_SERVER_URL to the dedicated local test server")
    server = make_url(configured)
    if server.database or server.host not in {"127.0.0.1", "localhost"} or server.port != 13396:
        raise ValueError("Migration tests require the dedicated 13396 server and no database")
    schema = "product_note_test_" + uuid.uuid4().hex
    admin = create_engine(server.render_as_string(hide_password=False))
    owner = None
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f"CREATE DATABASE `{schema}`"))
        target = server.set(database=schema).render_as_string(hide_password=False)
        monkeypatch.setenv("CATALOG_DATABASE_URL", target)
        owner = create_engine(target)
        yield owner, Config(str(ROOT / "dbs/catalog/alembic.ini"))
    finally:
        if owner is not None:
            await owner.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f"DROP DATABASE IF EXISTS `{schema}`"))
        await admin.dispose()


async def columns(engine, table):
    async with engine.connect() as connection:
        return await connection.run_sync(
            lambda sync: {entry["name"] for entry in inspect(sync).get_columns(table)}
        )


async def test_full_catalog_chain_upgrades_rolls_back_and_reupgrades(native_note_database):
    engine, config = native_note_database
    await asyncio.to_thread(command.upgrade, config, "0210")
    for table in TABLES:
        assert "source_reference" in await columns(engine, table)
    await asyncio.to_thread(command.upgrade, config, "head")
    for table in TABLES:
        assert "source_reference" not in await columns(engine, table)
    assert "source_reference" in await columns(engine, "tax_rate")
    await asyncio.to_thread(command.downgrade, config, "0210")
    for table in TABLES:
        assert "source_reference" in await columns(engine, table)
    await asyncio.to_thread(command.upgrade, config, "head")
    for table in TABLES:
        assert "source_reference" not in await columns(engine, table)


async def test_populated_columns_drop_without_losing_other_values(native_note_database):
    engine, config = native_note_database
    fixture_metadata = MetaData()
    fixture_tables = [
        Table(
            name,
            fixture_metadata,
            Column("id", Integer, primary_key=True),
            Column("amount", Numeric(19, 4), nullable=False),
            Column("selection_id", String(36), nullable=False),
            Column("source_reference", String(500), nullable=False),
        )
        for name in TABLES
    ]
    # Focused populated fixtures isolate the three DDL operations from unrelated
    # domain fixtures. The other test verifies the actual complete Catalog schema.
    async with engine.begin() as connection:
        await connection.run_sync(fixture_metadata.create_all)
        for table in fixture_tables:
            await connection.execute(
                table.insert(),
                {
                    "id": 7,
                    "amount": "123.4500",
                    "selection_id": "synthetic-selection",
                    "source_reference": "Retired synthetic note",
                },
            )
    await asyncio.to_thread(command.stamp, config, "0210")
    await asyncio.to_thread(command.upgrade, config, "0213")
    async with engine.connect() as connection:
        for table in fixture_tables:
            row = (
                await connection.execute(select(table.c.id, table.c.amount, table.c.selection_id))
            ).one()
            assert tuple(map(str, row)) == ("7", "123.4500", "synthetic-selection")
    for table in TABLES:
        assert "source_reference" not in await columns(engine, table)
    await asyncio.to_thread(command.downgrade, config, "0210")
    async with engine.connect() as connection:
        for table in fixture_tables:
            assert await connection.scalar(select(table.c.source_reference)) == ""
    await asyncio.to_thread(command.upgrade, config, "0213")
