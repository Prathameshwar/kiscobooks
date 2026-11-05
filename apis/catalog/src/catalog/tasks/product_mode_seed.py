"""Explicit compatibility seed from a complete operator-supplied Identity roster."""

import datetime as dt
import uuid
from typing import Literal

from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.product_authoring import CompanyProductAuthoringConfiguration as Mode
from catalog.tasks.classification import audit_change
from catalog.tasks.policy_state import company_policy_state
from catalog.tasks.product_mode import ENTITY, current


class LegacyCompany(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: uuid.UUID
    company_id: uuid.UUID


class LegacyRoster(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["identity-company-roster"]
    complete: Literal[True]
    cutoff_at: dt.datetime
    companies: list[LegacyCompany] = Field(max_length=100000)


async def seed(
    factory: async_sessionmaker[AsyncSession],
    roster: LegacyRoster,
    operator: uuid.UUID,
    *,
    apply: bool = False,
) -> int:
    if operator.int == 0:
        raise ValueError("seed requires a real operator identity")
    identities = {(row.tenant_id, row.company_id) for row in roster.companies}
    if len(identities) != len(roster.companies) or any(
        tenant.int == 0 or company.int == 0 for tenant, company in identities
    ):
        raise ValueError("roster contains duplicate or invalid identities")
    if roster.cutoff_at.tzinfo is None:
        raise ValueError("roster cutoff must include its timezone")
    inserted = 0
    for tenant, company in sorted(identities):
        with tenant_scope(tenant):
            async with factory.begin() as db:
                state = await company_policy_state(db, tenant, company, lock=apply)
                if await current(db, company) is not None:
                    continue  # Resumable; never overwrite an explicit operator/user choice.
                inserted += 1
                if not apply:
                    continue
                assert state is not None
                if state.generation >= 2**63 - 1:
                    raise ConflictError("Company policy generation exhausted")
                row = Mode(
                    id=uuid7(),
                    tenant_id=tenant,
                    company_id=company,
                    product_family_sku_enabled=True,
                    row_version=1,
                    change_reason="Compatibility roster " + roster.cutoff_at.isoformat(),
                    created_by=operator,
                    updated_by=operator,
                )
                db.add(row)
                state.generation += 1
                values = {
                    "product_family_sku_enabled": True,
                    "row_version": 1,
                    "change_reason": row.change_reason,
                }
                audit_change(
                    db,
                    Actor(tenant, operator),
                    company,
                    ENTITY,
                    row.id,
                    "create",
                    frozenset(values),
                    before={},
                    after=values,
                )
    return inserted
