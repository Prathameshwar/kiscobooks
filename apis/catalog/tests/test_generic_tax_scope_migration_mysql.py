"""Populated old rules keep their meaning; generic templates make rollback explicit."""

import asyncio

import pytest
from alembic import command
from sqlalchemy import text

from tests.test_product_commercial_note_migrations_mysql import native_note_database  # noqa: F401

pytestmark = pytest.mark.mysql


async def test_generic_scope_preserves_rules_and_guards_downgrade(native_note_database):  # noqa: F811
    engine, config = native_note_database
    async with engine.begin() as db:
        await db.execute(
            text("CREATE TABLE tax_rule (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL)")
        )
        await db.execute(text("INSERT INTO tax_rule (id, name) VALUES (7, 'Existing rule')"))
    await asyncio.to_thread(command.stamp, config, "0214")
    await asyncio.to_thread(command.upgrade, config, "0215")
    async with engine.begin() as db:
        assert (
            await db.execute(text("SELECT name, classification_scope FROM tax_rule WHERE id = 7"))
        ).one() == ("Existing rule", "SPECIFIC")
    await asyncio.to_thread(command.downgrade, config, "0214")
    await asyncio.to_thread(command.upgrade, config, "0215")
    async with engine.begin() as db:
        await db.execute(
            text(
                "INSERT INTO tax_rule (id, name, classification_scope) "
                "VALUES (8, 'Template', 'ANY')"
            )
        )
    with pytest.raises(RuntimeError, match="cannot downgrade Catalog"):
        await asyncio.to_thread(command.downgrade, config, "0214")
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "0215"
        assert await db.scalar(text("SELECT name FROM tax_rule WHERE id = 7")) == "Existing rule"


async def test_generic_defaults_on_native_catalog_schema(native_note_database, tenant_a):  # noqa: F811
    from billing_platform.db import create_session_factory

    from tests.test_tax_defaults import test_defaults_complete_exact_audited_and_repeatable

    engine, config = native_note_database
    await asyncio.to_thread(command.upgrade, config, "head")
    await test_defaults_complete_exact_audited_and_repeatable(
        create_session_factory(engine, guarded=True), tenant_a
    )
