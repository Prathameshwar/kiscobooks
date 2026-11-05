"""Scoped object loading shared by HTTP commands and durable workers."""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing_platform.db.base import Base
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.errors import NotFoundError, PermissionDeniedError


async def company_object[T: Base](
    db: AsyncSession,
    model: type[T],
    object_id: uuid.UUID,
    *,
    company_id: uuid.UUID,
    lock: bool = False,
) -> T:
    """Use an actual scoped SELECT, including on identity-map hits.

    Wrong tenant stays invisible; wrong company within that tenant is forbidden.
    Actor permissions are checked separately against the requested company.
    """
    tenant = require_current_tenant()
    if not all(hasattr(model, name) for name in ("id", "tenant_id", "company_id")):
        raise TypeError("company_object requires a tenant/company-owned model")
    stmt = (
        select(model)
        .where(cast(Any, model).id == object_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    row = await db.scalar(stmt)
    if row is None or cast(Any, row).tenant_id != tenant:
        raise NotFoundError("resource not found")
    if cast(Any, row).company_id != company_id:
        raise PermissionDeniedError("resource is outside the requested company")
    return row
