"""Native MySQL rehearsal for the single-DDL draft table and safe rollback."""

import asyncio

import httpx
import pytest
from alembic import command
from billing_platform.db import create_session_factory
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import text

from catalog.config import Settings
from catalog.main import create_app
from tests.conftest import ACTOR_SECRET
from tests.test_advanced_product_drafts import draft_body, prepared
from tests.test_pricing_dimension_migration_mysql import native_pricing_database  # noqa: F401

pytestmark = [pytest.mark.mysql, pytest.mark.usefixtures("stable_product_source_clock")]


async def test_native_draft_migration_and_retention_guard(native_pricing_database, tenant_a):  # noqa: F811
    engine, config = native_pricing_database
    await asyncio.to_thread(command.upgrade, config, "head")
    factory = create_session_factory(engine, guarded=True)
    app = create_app(Settings(actor_signing_secret=SecretStr(ACTOR_SECRET)), engine=engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://catalog.test"
        ) as client:
            _, _, auth, base, options = await prepared(client, factory, tenant_a)
            created = await client.post(
                base + "/drafts",
                headers={**auth, "Idempotency-Key": str(uuid7())},
                json=draft_body(options),
            )
            assert created.status_code == 201, created.text
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "0223"
        assert await db.scalar(text("SELECT COUNT(*) FROM advanced_product_draft")) == 1
    with pytest.raises(RuntimeError, match="advanced product drafts"):
        await asyncio.to_thread(command.downgrade, config, "0221")
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "0222"
