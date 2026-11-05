from __future__ import annotations

from collections.abc import AsyncIterator

from billing_platform.db import tenant_scope
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from audit.api.auth import Actor, actor


async def session(request: Request, current: Actor = Depends(actor)) -> AsyncIterator[AsyncSession]:
    """A session already scoped to the actor's tenant.

    The scope is set from the *verified* actor, never a request field, so every read is
    tenant-filtered by the session-level mechanism (CLAUDE.md §5.3) before a route runs.
    """
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise
