"""One company transaction for a bounded collection of ordinary commands.

Only the owner task can enlist. The context contains no grants and never bypasses
command authorization, receipts, field checks or audit. A caller may use a nested
transaction for a validation preview and roll it back before storing the review.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.db.tenant_context import get_current_tenant, tenant_scope


@dataclass(frozen=True, slots=True)
class Participation:
    session: AsyncSession
    factory: async_sessionmaker[AsyncSession]
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_id: uuid.UUID
    task: asyncio.Task[Any] | None


_participant: ContextVar[Participation | None] = ContextVar("command_participant", default=None)


def participating_session(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    company_id: uuid.UUID | None,
    actor_id: uuid.UUID,
) -> AsyncSession | None:
    value = _participant.get()
    if value is None:
        return None
    if (
        value.factory is not factory
        or (value.tenant_id, value.company_id, value.actor_id) != (tenant_id, company_id, actor_id)
        or get_current_tenant() != tenant_id
        or value.task is not asyncio.current_task()
        or not value.session.in_transaction()
    ):
        raise RuntimeError("command cannot join this transaction or task")
    return value.session


@asynccontextmanager
async def command_transaction(
    factory: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> AsyncIterator[AsyncSession]:
    if _participant.get() is not None or any(
        value.int == 0 for value in (tenant_id, company_id, actor_id)
    ):
        raise ValueError("command transaction requires an independent real company scope")
    with tenant_scope(tenant_id):
        async with factory() as db, db.begin():
            if db.get_bind().dialect.name == "sqlite":
                # Legacy SQLite starts a transaction only on DML. An explicit BEGIN
                # makes an initial SAVEPOINT belong to the root transaction as on MySQL.
                connection = await db.connection()
                await connection.exec_driver_sql("BEGIN")
            token = _participant.set(
                Participation(db, factory, tenant_id, company_id, actor_id, asyncio.current_task())
            )
            try:
                yield db
            finally:
                _participant.reset(token)
