"""Dev-only migration smoke runner against a live MySQL server.

NOT a test and NOT part of the suite. The authoritative migration proof is the ``@mysql``
round-trip test in ``tests/test_models_and_migrations.py`` against MySQL 9.6 (via
testcontainers in CI). This helper exists because this workstation has no Docker but does
have a MySQL 9.6 server — it runs the real Alembic chain ``upgrade head`` then ``downgrade
base`` against a throwaway schema so the hand-written DDL is exercised by a real server
rather than only by SQLite's ``create_all``. For ``audit`` that specifically proves the
RANGE-partitioned ``audit_event`` (composite PK, ``BINARY(32)`` hashes, monthly partitions
+ ``pmax``) is accepted — none of which SQLite can express.

Usage (from apis/audit):
    uv run python tools/mysql_smoke.py
Environment:
    AUDIT_SMOKE_SERVER_URL  async URL to the server, no database, e.g.
        mysql+asyncmy://root:pwd@127.0.0.1:3306
    AUDIT_SMOKE_DB          throwaway database name (default: audit_smoke)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from audit.metadata import TABLES  # the service's own tables, not the shared registry

DBS_DIR = Path(__file__).resolve().parents[2].parent / "dbs" / "audit"
ALEMBIC_INI = DBS_DIR / "alembic.ini"


def _config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(DBS_DIR))
    # configparser reads a bare `%` (e.g. `%40` for `@` in a url-encoded password) as
    # interpolation; `%%` resolves back to a single `%`.
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


async def _partition_names(url: str) -> set[str]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT PARTITION_NAME FROM information_schema.PARTITIONS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'audit_event' "
                    "AND PARTITION_NAME IS NOT NULL"
                )
            )
            return {row[0] for row in result}
    finally:
        await engine.dispose()


def main() -> int:
    # No default: a DB URL carries a password, and a default would put a real credential in
    # the repo (CLAUDE.md §5.9). Set AUDIT_SMOKE_SERVER_URL in the environment, e.g.
    #   export AUDIT_SMOKE_SERVER_URL='mysql+asyncmy://root:<pwd>@127.0.0.1:3306'
    server_url = os.environ.get("AUDIT_SMOKE_SERVER_URL")
    if not server_url:
        print("set AUDIT_SMOKE_SERVER_URL (async server URL, no database) to run the smoke")
        return 2
    db = os.environ.get("AUDIT_SMOKE_DB", "audit_smoke")
    db_url = f"{server_url}/{db}"

    asyncio.run(_reset_schema(server_url, db))
    config = _config(db_url)

    command.upgrade(config, "head")
    after_upgrade = asyncio.run(_table_names(db_url))
    missing = TABLES - after_upgrade
    if missing:
        print(f"FAIL: upgrade head did not create: {sorted(missing)}")
        return 1

    partitions = asyncio.run(_partition_names(db_url))
    if "pmax" not in partitions or "p202609" not in partitions:
        print(f"FAIL: audit_event partitions look wrong: {sorted(partitions)}")
        return 1
    print(
        f"upgrade head OK — {len(after_upgrade)} tables, "
        f"{len(partitions)} audit_event partitions (incl. pmax)"
    )

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
