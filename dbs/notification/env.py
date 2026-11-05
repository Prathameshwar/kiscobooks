"""Alembic environment for the notification database."""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _src in (_ROOT / "libs" / "platform" / "src", _ROOT / "apis" / "notification" / "src"):
    if str(_src) not in sys.path:
        sys.path.append(str(_src))

from notification.metadata import service_metadata  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = service_metadata()


def _database_url() -> str:
    url = config.attributes.get("database_url") or os.environ.get("NOTIFICATION_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("NOTIFICATION_DATABASE_URL must be an async MariaDB URL")
    return url


_OPTIONS = {
    "target_metadata": target_metadata,
    "compare_type": True,
    "compare_server_default": True,
    "transaction_per_migration": True,
}


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), literal_binds=True, dialect_opts={}, **_OPTIONS)
    with context.begin_transaction():
        context.run_migrations()


def _migrate(connection: Connection) -> None:
    context.configure(connection=connection, **_OPTIONS)
    with context.begin_transaction():
        context.run_migrations()


async def _async_migrate() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    engine = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_migrate)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_async_migrate())
