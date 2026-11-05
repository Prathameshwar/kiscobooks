"""Bounded expiry sweep; hard expiry is enforced on every request independently."""

from __future__ import annotations

import asyncio

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.tenant_context import unfiltered
from billing_platform.db.types import utcnow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.api.auth import Actor
from identity.api.security import lock_tenant
from identity.config import Settings
from identity.models import ImpersonationSession
from identity.services.audit import record


async def expire_batch(factory: async_sessionmaker[AsyncSession], limit: int = 100) -> int:
    if not 1 <= limit <= 100:
        raise ValueError("expiry batch must be between 1 and 100")
    with unfiltered():
        async with factory() as db:
            candidates = list(
                await db.execute(
                    select(ImpersonationSession.tenant_id, ImpersonationSession.id)
                    .where(
                        ImpersonationSession.ended_at.is_(None),
                        ImpersonationSession.expires_at <= utcnow(),
                    )
                    .order_by(ImpersonationSession.expires_at, ImpersonationSession.id)
                    .limit(limit)
                )
            )
    count = 0
    for tenant_id, session_id in candidates:
        with tenant_scope(tenant_id):
            async with factory() as db, db.begin():
                await lock_tenant(db, tenant_id)
                row = await db.get(ImpersonationSession, session_id)
                if row is None or row.ended_at is not None or row.expires_at > utcnow():
                    continue
                row.ended_at, row.ended_reason = row.expires_at, "expired"
                record(
                    db,
                    Actor(tenant_id, row.actor_user_id),
                    action="user.impersonation_expired",
                    entity="impersonation_session",
                    entity_id=row.id,
                    changes={"user_id": {"to": str(row.target_user_id)}},
                )
                count += 1
    return count


async def run(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    try:
        while True:
            await expire_batch(create_session_factory(engine))
            await asyncio.sleep(30)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(Settings()))  # type: ignore[call-arg]  # required settings are read from environment
