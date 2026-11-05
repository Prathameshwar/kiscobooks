"""Dev-only migration smoke runner against a live MySQL server.

NOT a test and NOT part of the suite. The authoritative migration proof is the
``@mysql`` round-trip test in ``tests/test_migrations.py`` against MySQL 9.6 (via
testcontainers in CI). This helper exists because this workstation has no Docker but
does have a MySQL 9.6 server — it runs the real Alembic chain ``upgrade head`` then
``downgrade base`` against a throwaway schema so hand-written DDL (VARCHAR lengths,
64-char index names, composite FKs, ROW_FORMAT) is exercised by a real server rather
than only by SQLite's ``create_all``.

A green run here means "the DDL executes and reverses on MySQL 9.6" — the platform's
datastore (tech-stack.md decision log, 2026-09-11). It does not replace the
containerised ``@mysql`` drift test in CI, which also checks that the applied schema
matches the models exactly.

Usage (from apis/identity):
    uv run python tools/mysql_smoke.py
Environment:
    IDENTITY_SMOKE_SERVER_URL  async URL to the server, no database, e.g.
        mysql+asyncmy://root:pwd@127.0.0.1:3306
    IDENTITY_SMOKE_DB          throwaway database name (default: identity_smoke)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from billing_platform.db import Base
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from identity import models  # noqa: F401  registers tables on Base.metadata

DBS_DIR = Path(__file__).resolve().parents[2].parent / "dbs" / "identity"
ALEMBIC_INI = DBS_DIR / "alembic.ini"


def _config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(DBS_DIR))
    # configparser interprets a bare `%` (e.g. `%40` for `@` in a url-encoded
    # password) as interpolation syntax; `%%` resolves back to a single `%`.
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


async def _reset_schema(server_url: str, db: str) -> None:
    engine = create_async_engine(server_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {db}"))
            await conn.execute(
                text(f"CREATE DATABASE {db} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            )
    finally:
        await engine.dispose()


async def _table_names(url: str) -> set[str]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
    finally:
        await engine.dispose()


def main() -> int:
    # No default: a DB URL carries a password, and a default would put a real credential
    # in the repo (CLAUDE.md §5.9). Set IDENTITY_SMOKE_SERVER_URL in the environment, e.g.
    #   export IDENTITY_SMOKE_SERVER_URL='mysql+asyncmy://root:<pwd>@127.0.0.1:3306'
    server_url = os.environ.get("IDENTITY_SMOKE_SERVER_URL")
    if not server_url:
        print("set IDENTITY_SMOKE_SERVER_URL (async server URL, no database) to run the smoke")
        return 2
    db = os.environ.get("IDENTITY_SMOKE_DB", "identity_smoke")
    db_url = f"{server_url}/{db}"

    asyncio.run(_reset_schema(server_url, db))
    config = _config(db_url)

    command.upgrade(config, "head")
    after_upgrade = asyncio.run(_table_names(db_url))
    missing = set(Base.metadata.tables) - after_upgrade
    if missing:
        print(f"FAIL: upgrade head did not create: {sorted(missing)}")
        return 1
    print(f"upgrade head OK — {len(after_upgrade)} tables (incl. alembic_version)")

    command.downgrade(config, "base")
    after_downgrade = asyncio.run(_table_names(db_url))
    leftover = after_downgrade - {"alembic_version"}
    if leftover:
        print(f"FAIL: downgrade base left tables behind: {sorted(leftover)}")
        return 1
    print("downgrade base OK — schema clean")
    print("SMOKE PASS (MySQL 9.6; containerised @mysql drift test remains CI-pending)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
