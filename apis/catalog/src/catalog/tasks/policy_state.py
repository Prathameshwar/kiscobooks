"""One company policy lock shared by Catalog commands and derived-state transitions."""

import uuid

from billing_platform.db.claims import insert_candidate
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.errors import PermissionDeniedError
from billing_platform.gateway import Actor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.classification import CatalogPolicyState


async def policy_state(
    db: AsyncSession, actor: Actor, company: uuid.UUID, *, lock: bool = False
) -> CatalogPolicyState | None:
    return await company_policy_state(db, actor.tenant_id, company, lock=lock)


async def company_policy_state(
    db: AsyncSession, tenant: uuid.UUID, company: uuid.UUID, *, lock: bool = False
) -> CatalogPolicyState | None:
    if tenant != require_current_tenant():
        raise PermissionDeniedError("policy lock belongs to another tenant")
    stmt = select(CatalogPolicyState).where(CatalogPolicyState.company_id == company)
    if lock:
        await insert_candidate(
            db,
            CatalogPolicyState,
            {"tenant_id": tenant, "company_id": company, "generation": 1},
        )
        stmt = stmt.with_for_update()
    row = await db.scalar(stmt.execution_options(populate_existing=True))
    assert row is None or isinstance(row, CatalogPolicyState)
    return row
