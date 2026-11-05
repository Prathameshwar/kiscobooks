from collections.abc import AsyncGenerator

from billing_platform.db import tenant_scope
from billing_platform.gateway import Actor
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor


async def session(
    request: Request, current: Actor = Depends(actor)
) -> AsyncGenerator[AsyncSession, None]:
    """Bind the verified tenant for the entire transaction, including commit/rollback."""
    with tenant_scope(current.tenant_id):
        async with request.app.state.session_factory() as db:
            async with db.begin():
                yield db
