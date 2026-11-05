from __future__ import annotations

from collections.abc import AsyncIterator

from billing_platform.db import tenant_scope
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from notification.api.auth import Actor, actor
from notification.models import NotificationSpace
from notification.ownership import space_scope


async def session(request: Request, current: Actor = Depends(actor)) -> AsyncIterator[AsyncSession]:
    space = request.app.state.settings.platform_space_id if current.platform else current.tenant_id
    assert space is not None
    with tenant_scope(current.tenant_id), space_scope(space):
        async with request.app.state.session_factory() as db:
            db.info["notification_actor_id"] = current.user_id
            try:
                if request.method not in {"GET", "HEAD", "OPTIONS"}:
                    root = await db.get(NotificationSpace, space, with_for_update=True)
                    if root is None:
                        db.add(
                            NotificationSpace(
                                id=space,
                                tenant_id=current.tenant_id,
                                kind="platform" if current.platform else "tenant",
                            )
                        )
                        await db.flush()
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise
