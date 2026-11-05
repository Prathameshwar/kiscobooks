"""Single-row unique-key claims that never modify an existing row.

The insert starts a real database write transaction before any later rollback.
Unlike a first SAVEPOINT, this also preserves outer rollback on SQLite's legacy
transaction mode. Services still verify the exact claimed row and content.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import Insert

from billing_platform.db.base import Base
from billing_platform.db.guarded import GuardedSession
from billing_platform.db.mixins import TenantMixin
from billing_platform.db.tenant_context import (
    TenantContextError,
    require_current_tenant,
    unfiltered,
)


def candidate_statement(dialect: str, model: type[Base], values: Mapping[str, Any]) -> Insert:
    if not issubclass(model, TenantMixin) or "id" not in model.__table__.columns:
        raise TypeError("unique candidates require a scoped UUID identity")
    if dialect in {"mysql", "mariadb"}:
        statement = mysql_insert(model).values(**values)
        return statement.on_duplicate_key_update(id=model.__table__.c.id)
    if dialect == "sqlite":
        return sqlite_insert(model).values(**values).on_conflict_do_nothing()
    raise ValueError("unsupported claim database")


async def insert_candidate(db: AsyncSession, model: type[Base], values: Mapping[str, Any]) -> None:
    tenant = require_current_tenant()
    if values.get("tenant_id") != tenant:
        raise TenantContextError("candidate must belong to the current tenant")
    if not db.in_transaction():
        raise RuntimeError("candidate requires the caller's transaction")
    if isinstance(db.sync_session, GuardedSession):
        db.sync_session.tenant()
    statement = candidate_statement(db.get_bind().dialect.name, model, values)
    # Reviewed single INSERT, verified tenant, and immutable duplicate branch.
    # This is not a general bulk-DML bypass and never accepts client SQL.
    with unfiltered():
        await db.execute(statement)
