"""Alembic environment for the `audit` service.

**All path wiring for this service's migrations lives here and nowhere else**
(CLAUDE.md §4). Models live under ``apis/audit/src/audit/models/``; revisions live in
``versions/`` next to this file.

The database URL comes from ``AUDIT_DATABASE_URL`` in the environment, never from
``alembic.ini`` — a URL in the ini is a credential in the repo (CLAUDE.md §5.9). Note
the migration grant differs from the runtime grant: migrations need DDL, while the
service's own user holds only INSERT and SELECT (docs/audit.md §4.1).
"""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import TypedDict

from alembic import context
from sqlalchemy import Connection, MetaData, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

_HERE = Path(__file__).resolve().parent  # dbs/audit
_ROOT = _HERE.parent.parent  # repo root

# Appended, not prepended: an installed distribution wins, so this is only a fallback
# for running `alembic` without an editable install. Prepending would risk importing
# the same module under two paths.
for _src in (_ROOT / "libs" / "platform" / "src", _ROOT / "apis" / "audit" / "src"):
    if str(_src) not in sys.path:
        sys.path.append(str(_src))

from audit import models  # noqa: E402,F401  registers every model on Base.metadata
from audit.metadata import service_metadata  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

#: Include Audit's platform tables without importing unrelated service ownership.
target_metadata = service_metadata()

_URL_ENV_VAR = "AUDIT_DATABASE_URL"


def _database_url() -> str:
    url = os.environ.get(_URL_ENV_VAR) or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError(
            f"{_URL_ENV_VAR} is not set. Migrations need an async MySQL URL, "
            "e.g. mysql+asyncmy://audit_ddl:...@localhost:3306/audit — set it in the "
            "environment or the secret manager, never in alembic.ini."
        )
    return url


#: Passed to both offline and online runs so the two agree.
class _MigrationOptions(TypedDict):
    target_metadata: MetaData
    compare_type: bool
    compare_server_default: bool
    transaction_per_migration: bool


_CONTEXT_OPTIONS: _MigrationOptions = {
    "target_metadata": target_metadata,
    # MySQL is where a VARCHAR length or a DECIMAL scale drifts silently.
    "compare_type": True,
    "compare_server_default": True,
    # No transactional DDL on MySQL (rule 4.8): one revision per DDL statement, each
    # committed on its own, so a failure leaves the version table truthful.
    "transaction_per_migration": True,
}


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a connection, for review or a DBA-applied change."""
    context.configure(
        url=_database_url(), literal_binds=True, dialect_opts={}, **_CONTEXT_OPTIONS
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, **_CONTEXT_OPTIONS)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    engine = async_engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    """Run against a live database.

    ``asyncio.run`` unconditionally: the round-trip test drives Alembic through its
    Python API from a synchronous test, so there is never a running loop here.
    """
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
