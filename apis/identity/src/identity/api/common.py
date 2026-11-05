"""Small helpers shared across route modules.

Kept here rather than copied per module (CLAUDE.md §3, the same reason the keyset helper
is shared): loading a company by id, in the actor's tenant, is done by four route
modules and must behave identically in all of them.
"""

from __future__ import annotations

import uuid

from billing_platform.errors import NotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Company


async def load_company(
    db: AsyncSession, company_id: uuid.UUID, *, for_update: bool = False
) -> Company:
    """Fetch a company in the actor's tenant, or 404.

    A company in another tenant is invisible to the session filter, so this returns
    ``None`` and the caller 404s — cross-tenant access never even reaches the
    object-scope check. Wrong-*company*-within-tenant is what that check handles.
    """
    if for_update:
        row = await db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    else:
        row = await db.get(Company, company_id)
    if row is None:
        raise NotFoundError("company not found")
    return row
