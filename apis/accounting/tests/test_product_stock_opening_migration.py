"""Native MySQL preserves the company row and enforces product opening uniqueness."""

import asyncio
import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from billing_platform.db import create_engine
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError


async def test_native_product_opening_migration(monkeypatch):
    from accounting.metadata import service_metadata

    configured = os.getenv("ACCOUNTING_TEST_MYSQL_SERVER_URL")
    if not configured:
        pytest.skip("Requires the isolated native MySQL server on port 13398")
    server = make_url(configured)
    if server.database or server.host != "127.0.0.1" or server.port != 13398:
        raise ValueError("Use the dedicated loopback test server")
    schema = "accounting_test_" + uuid.uuid4().hex
    admin = create_engine(configured)
    engine = None
    try:
        async with admin.begin() as db:
            await db.execute(text(f"CREATE DATABASE `{schema}`"))
        url = server.set(database=schema).render_as_string(hide_password=False)
        monkeypatch.setenv("ACCOUNTING_DATABASE_URL", url)
        engine = create_engine(url)
        config = Config(str(Path(__file__).resolve().parents[3] / "dbs/accounting/alembic.ini"))
        config.set_main_option(
            "script_location", str(Path(__file__).resolve().parents[3] / "dbs/accounting")
        )
        await asyncio.to_thread(command.upgrade, config, "0231")
        tenant, company = uuid.uuid4().bytes, uuid.uuid4().bytes
        values = {"tenant": tenant, "company": company, "id": uuid.uuid4().bytes}
        async with engine.begin() as db:
            await db.execute(
                text(
                    "INSERT INTO stock_opening_control (id, tenant_id, company_id, currency, "
                    "books_begin_date, status, row_version, manifest, manifest_hash, created_at, "
                    "updated_at) VALUES (:id, :tenant, :company, 'INR', '2026-04-01', 'FINALIZED', "
                    "1, '{}', REPEAT('a',64), UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))"
                ),
                values,
            )
        await asyncio.to_thread(command.upgrade, config, "head")
        async with engine.connect() as db:
            existing = (
                await db.execute(
                    text("SELECT item_id, company_slot, status FROM stock_opening_control")
                )
            ).one()
            assert tuple(existing) == (None, 1, "FINALIZED")
            assert (
                await db.run_sync(
                    lambda connection: compare_metadata(
                        MigrationContext.configure(connection), service_metadata()
                    )
                )
                == []
            )
        await asyncio.to_thread(command.downgrade, config, "0231")
        await asyncio.to_thread(command.upgrade, config, "head")
        product = values | {"id": uuid.uuid4().bytes, "item": uuid.uuid4().bytes}
        insert = text(
            "INSERT INTO stock_opening_control (id, tenant_id, company_id, item_id, company_slot, "
            "currency, books_begin_date, status, row_version, manifest, manifest_hash, created_at, "
            "updated_at) VALUES (:id, :tenant, :company, :item, NULL, 'INR', '2026-04-01', 'OPEN', "
            "1, '{}', REPEAT('a',64), UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))"
        )
        async with engine.begin() as db:
            await db.execute(insert, product)
        with pytest.raises(IntegrityError):
            async with engine.begin() as db:
                await db.execute(insert, product | {"id": uuid.uuid4().bytes})
        with pytest.raises(RuntimeError, match="cannot discard"):
            await asyncio.to_thread(command.downgrade, config, "0231")
    finally:
        if engine:
            await engine.dispose()
        async with admin.begin() as db:
            await db.execute(text(f"DROP DATABASE `{schema}`"))
        await admin.dispose()
