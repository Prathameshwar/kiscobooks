"""Native MySQL GST/activation validation in a disposable loopback test schema."""

import asyncio
import datetime as dt
import json
import os
import uuid
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import Connection, text
from sqlalchemy.engine import make_url

from catalog.config import Settings
from catalog.main import create_app
from catalog.metadata import MIGRATION_HEAD, TABLES, service_metadata
from catalog.tasks import activation
from tests.conftest import ACTOR_SECRET
from tests.tax_factories import DATE, seed_tax
from tests.test_activation import test_reviewed_activation_freezes_structure_and_replays_once
from tests.test_activation_edges import test_service_activation_never_creates_inventory
from tests.test_commercial_api import command_headers
from tests.test_tax_security import test_all_eleven_tables_are_tenant_isolated_and_decimal
from tests.test_tax_workflows import test_tax_publication_is_dated_atomic_and_replayable
from tools.mysql_smoke import schema

ROOT = Path(__file__).resolve().parents[3]


async def verify(url: str) -> dict[str, object]:
    app = create_app(Settings(database_url=url, actor_signing_secret=SecretStr(ACTOR_SECRET)))
    try:
        async with app.router.lifespan_context(app):
            async with app.state.engine.connect() as connection:

                def differences(sync: Connection) -> list[object]:
                    return list(
                        compare_metadata(MigrationContext.configure(sync), service_metadata())
                    )

                drift = await connection.run_sync(differences)
                assert not drift, drift
                version = await connection.scalar(text("SELECT VERSION()"))
            factory = app.state.session_factory
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://catalog.test",
            ) as client:
                await test_tax_publication_is_dated_atomic_and_replayable(client, factory, uuid7())
                with pytest.MonkeyPatch.context() as patch:
                    patch.setattr(
                        activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC)
                    )
                    await test_reviewed_activation_freezes_structure_and_replays_once(
                        client, factory, uuid7(), patch
                    )
                    await test_service_activation_never_creates_inventory(
                        client, factory, uuid7(), patch
                    )
                    await test_all_eleven_tables_are_tenant_isolated_and_decimal(
                        client, factory, uuid7(), uuid7(), patch
                    )
                    for same_key in (False, True):
                        root, auth, ids = await seed_tax(factory, uuid7())
                        path = root + "/items/" + str(ids["item"])
                        preview = await client.post(
                            path + "/activation-preview", headers=auth, json={"as_of": str(DATE)}
                        )
                        assert (
                            preview.status_code == 200 and preview.json()["eligible"]
                        ), preview.text
                        body = {
                            key: preview.json()[key]
                            for key in (
                                "as_of",
                                "expected_version",
                                "expected_family_version",
                                "preview_token",
                            )
                        }
                        first = command_headers(auth)
                        second = first if same_key else command_headers(auth)
                        replies = await asyncio.gather(
                            *(
                                client.post(path + "/activate", headers=entry, json=body)
                                for entry in (first, second)
                            )
                        )
                        assert sorted(entry.status_code for entry in replies) == (
                            [200, 200] if same_key else [200, 409]
                        ), [entry.text for entry in replies]
        return {
            "server_version": version,
            "head": MIGRATION_HEAD,
            "tables": len(TABLES),
            "schema_drift": [],
            "tax_publication": "passed",
            "goods_and_service_activation": "passed",
            "tenant_isolation_tables": 11,
            "activation_races": 2,
        }
    finally:
        await app.state.engine.dispose()


def main() -> None:
    server = os.environ["CATALOG_TEST_MYSQL_SERVER_URL"]
    parsed = make_url(server)
    if (
        parsed.drivername != "mysql+asyncmy"
        or parsed.host not in {"localhost", "127.0.0.1", "::1"}
        or parsed.database
    ):
        raise ValueError("test server must be loopback without an existing database")
    database = "catalog_test_" + uuid.uuid4().hex
    url = parsed.set(database=database).render_as_string(hide_password=False)
    cfg = Config(str(ROOT / "dbs/catalog/alembic.ini"))
    previous = os.environ.get("CATALOG_DATABASE_URL")
    created = False
    try:
        asyncio.run(schema(server, database, create=True))
        created = True
        os.environ["CATALOG_DATABASE_URL"] = url
        command.upgrade(cfg, "head")
        result = asyncio.run(verify(url))
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
        result["roundtrip"] = "upgrade/head, downgrade/base, upgrade/head"
        print(json.dumps(result, sort_keys=True))
    finally:
        if previous is None:
            os.environ.pop("CATALOG_DATABASE_URL", None)
        else:
            os.environ["CATALOG_DATABASE_URL"] = previous
        if created:
            asyncio.run(schema(server, database, create=False))


if __name__ == "__main__":
    main()
