"""Run report authorization contracts on a new, disposable loopback MySQL schema."""

import asyncio
import os
import re
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from billing_platform.db import create_engine
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url

from identity.config import Settings
from identity.main import create_app
from tests.api_support import ACTOR_SECRET, CURSOR_SECRET
from tests.test_report_authorizations import (
    test_signed_worker_proof_rechecks_revocation_and_current_field_denies,
)
from tests.test_report_company_context import (
    test_report_context_includes_report_and_accounting_read_denies,
)

ROOT = Path(__file__).resolve().parents[3]


async def schema(server: str, name: str, *, create: bool) -> None:
    if not re.fullmatch(r"identity_report_test_[0-9a-f]{32}", name):
        raise ValueError("only this tool's disposable schema is allowed")
    engine = create_engine(server)
    try:
        async with engine.connect() as db:
            await db.execute(
                text(
                    f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    if create
                    else f"DROP DATABASE `{name}`"
                )
            )
    finally:
        await engine.dispose()


async def verify(url: str, *, context: bool) -> None:
    app = create_app(
        Settings(
            database_url=url,
            actor_signing_secret=SecretStr(ACTOR_SECRET),
            cursor_signing_secret=SecretStr(CURSOR_SECRET),
            public_auth_url="https://auth.test",
        )
    )
    try:
        async with app.state.session_factory() as db:
            if context:
                await test_report_context_includes_report_and_accounting_read_denies(
                    db, uuid.uuid4(), uuid.uuid4()
                )
            else:
                await test_signed_worker_proof_rechecks_revocation_and_current_field_denies(
                    app, db, uuid.uuid4(), uuid.uuid4()
                )
        print("PASS: native report " + ("gateway policies" if context else "worker authority"))
    finally:
        await app.state.engine.dispose()
        await app.state.oidc_http.aclose()


def scenario(*, context: bool) -> None:
    server = os.environ.get(
        "IDENTITY_TEST_MYSQL_SERVER_URL", "mysql+asyncmy://root@127.0.0.1:13396"
    )
    parsed = make_url(server)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or parsed.database:
        raise ValueError("loopback server without an existing database is required")
    name = "identity_report_test_" + uuid.uuid4().hex
    url = parsed.set(database=name).render_as_string(hide_password=False)
    config = Config(str(ROOT / "dbs/identity/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "dbs/identity"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    asyncio.run(schema(server, name, create=True))
    previous = os.environ.get("IDENTITY_DATABASE_URL")
    os.environ["IDENTITY_DATABASE_URL"] = url
    try:
        command.upgrade(config, "head")
        asyncio.run(verify(url, context=context))
    finally:
        if previous is None:
            os.environ.pop("IDENTITY_DATABASE_URL", None)
        else:
            os.environ["IDENTITY_DATABASE_URL"] = previous
        asyncio.run(schema(server, name, create=False))


def main() -> None:
    for context in (False, True):
        scenario(context=context)


if __name__ == "__main__":
    main()
