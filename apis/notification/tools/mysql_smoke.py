"""Dev-only migration smoke runner for `notification` against a live MySQL server.

NOT a test. The authoritative proof is the containerised ``@mysql`` round-trip in the
suite (CI). This runs the real Alembic chain ``upgrade head`` then ``downgrade base``
against a throwaway schema so hand-written DDL is exercised by a real server rather than
only by SQLite's ``create_all``. A green run means the DDL executes and reverses on MySQL
9.6 — the platform datastore (tech-stack.md decision log, 2026-09-11).

Usage (from apis/notification):
    NOTIFICATION_SMOKE_SERVER_URL='mysql+asyncmy://root:<pwd>@127.0.0.1:3306' \
        uv run python tools/mysql_smoke.py
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

# notification owns a subset of Base.metadata (no reference/idempotency tables), so the
# check is against its own table set, not the shared metadata.
from notification.metadata import TABLES

DBS_DIR = Path(__file__).resolve().parents[2].parent / "dbs" / "notification"
ALEMBIC_INI = DBS_DIR / "alembic.ini"


def _config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(DBS_DIR))
    # configparser reads `%` as interpolation; `%%` resolves back to one `%`.
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
    server_url = os.environ.get("NOTIFICATION_SMOKE_SERVER_URL")
    if not server_url:
        print("set NOTIFICATION_SMOKE_SERVER_URL (async server URL, no database) to run the smoke")
        return 2
    db = os.environ.get("NOTIFICATION_SMOKE_DB", "notification_smoke")
    db_url = f"{server_url}/{db}"

    asyncio.run(_reset_schema(server_url, db))
    config = _config(db_url)

    command.upgrade(config, "head")
    after_upgrade = asyncio.run(_table_names(db_url))
    missing = set(TABLES) - after_upgrade
    if missing:
        print(f"FAIL: upgrade head did not create: {sorted(missing)}")
        return 1
    print(f"upgrade head OK - {len(after_upgrade)} tables (incl. alembic_version)")

    command.downgrade(config, "base")
    leftover = asyncio.run(_table_names(db_url)) - {"alembic_version"}
    if leftover:
        print(f"FAIL: downgrade base left tables behind: {sorted(leftover)}")
        return 1
    print("downgrade base OK - schema clean")
    print("SMOKE PASS (MySQL 9.6; containerised @mysql drift test remains CI-pending)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
