"""Model-option migration preserves history and refuses lossy rollback."""

import asyncio

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.test_pricing_dimension_migration_mysql import native_pricing_database  # noqa: F401

pytestmark = pytest.mark.mysql


async def test_model_option_native_migration(native_pricing_database):  # noqa: F811
    engine, config = native_pricing_database
    async with engine.begin() as db:
        await db.execute(
            text(
                "CREATE TABLE product_entry_option_policy "
                "(id INTEGER PRIMARY KEY, brand_mode VARCHAR(10) NOT NULL)"
            )
        )
        await db.execute(text("INSERT INTO product_entry_option_policy VALUES (1, 'REQUIRED')"))
    await asyncio.to_thread(command.stamp, config, "0216")
    await asyncio.to_thread(command.upgrade, config, "0217")
    async with engine.connect() as db:
        row = (await db.execute(text("SELECT * FROM product_entry_option_policy"))).mappings().one()
        assert row["brand_mode"] == "REQUIRED"
        assert row["model_mode"] == "INHERIT" and row["model_default"] is None
    await asyncio.to_thread(command.downgrade, config, "0216")
    await asyncio.to_thread(command.upgrade, config, "0217")
    with pytest.raises(DBAPIError, match="entry_model_mode"):
        async with engine.begin() as db:
            await db.execute(text("UPDATE product_entry_option_policy SET model_mode = 'OPTIONAL'"))
    async with engine.begin() as db:
        await db.execute(text("UPDATE product_entry_option_policy SET model_mode = 'DISABLED'"))
    with pytest.raises(RuntimeError, match="cannot discard authored"):
        await asyncio.to_thread(command.downgrade, config, "0216")
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "0217"
