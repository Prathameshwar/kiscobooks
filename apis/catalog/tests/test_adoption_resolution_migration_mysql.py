"""Additive versioning preserves old pins and prevents unsafe rollback of new pins."""

import asyncio
import datetime as dt

import pytest
from alembic import command
from sqlalchemy import Column, Date, Integer, LargeBinary, MetaData, Table, select, text

from tests.test_product_commercial_note_migrations_mysql import (
    columns,
    native_note_database,  # noqa: F401
)

pytestmark = pytest.mark.mysql


async def test_complete_catalog_adoption_version_migration(native_note_database):  # noqa: F811
    engine, config = native_note_database
    await asyncio.to_thread(command.upgrade, config, "0213")
    original = await columns(engine, "product_configuration_adoption")
    assert "resolution_version" not in original
    await asyncio.to_thread(command.upgrade, config, "head")
    assert await columns(engine, "product_configuration_adoption") == original | {
        "resolution_version"
    }
    await asyncio.to_thread(command.downgrade, config, "0213")
    assert await columns(engine, "product_configuration_adoption") == original
    await asyncio.to_thread(command.upgrade, config, "head")


async def test_populated_adoption_history_is_preserved_and_new_pins_block_rollback(
    native_note_database,  # noqa: F811
):
    engine, config = native_note_database
    metadata = MetaData()
    old = Table(
        "product_configuration_adoption",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("revision", Integer, nullable=False),
        Column("effective_on", Date, nullable=False),
        Column("source_version", Integer, nullable=False),
        Column("preview_hash", LargeBinary(32), nullable=False),
    )
    evidence = {
        "id": 7,
        "revision": 1,
        "effective_on": dt.date(2090, 1, 1),
        "source_version": 9,
        "preview_hash": bytes(range(32)),
    }
    # Synthetic populated rows isolate the additive DDL; the other test checks
    # the real complete migration chain. Only the dedicated disposable DB is used.
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
        await connection.execute(old.insert(), evidence)
    await asyncio.to_thread(command.stamp, config, "0213")
    await asyncio.to_thread(command.upgrade, config, "0214")
    async with engine.begin() as connection:
        original = (await connection.execute(select(old))).mappings().one()
        assert dict(original) == evidence
        assert (
            await connection.scalar(
                text("SELECT resolution_version FROM product_configuration_adoption WHERE id = 7")
            )
            == 1
        )
    # Old-only rows permit rollback and reupgrade with all evidence unchanged.
    await asyncio.to_thread(command.downgrade, config, "0213")
    await asyncio.to_thread(command.upgrade, config, "0214")
    async with engine.begin() as connection:
        await connection.execute(old.insert(), {**evidence, "id": 8, "revision": 2})
        await connection.execute(
            text("UPDATE product_configuration_adoption SET resolution_version = 2 WHERE id = 8")
        )
    with pytest.raises(RuntimeError, match="cannot downgrade Catalog"):
        await asyncio.to_thread(command.downgrade, config, "0213")
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0214"
        assert list(
            (
                await connection.execute(
                    text(
                        "SELECT id, resolution_version FROM product_configuration_adoption "
                        "ORDER BY id"
                    )
                )
            ).tuples()
        ) == [(7, 1), (8, 2)]
        assert (
            dict((await connection.execute(select(old).where(old.c.id == 7))).mappings().one())
            == evidence
        )
