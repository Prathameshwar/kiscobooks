"""Field-policy and audit boundary for financial domain records."""

from typing import Any

from billing_platform.errors import PermissionDeniedError
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.masters import Record
from accounting.resources import BY_NAME
from accounting.tasks.access import authorize, readable, writable
from accounting.tasks.commands import audit, values_of


def require_fields(
    access: Access, name: str, fields: set[str], *, row: Record | None = None
) -> None:
    spec = (BY_NAME | FINANCIAL_BY_NAME)[name]
    authorize(access, spec, "read")
    if not fields <= readable(access, spec, values_of(row, spec) if row is not None else None):
        raise PermissionDeniedError("financial calculation inputs are not readable")


async def create_row(db: AsyncSession, access: Access, name: str, **values: Any) -> Record:
    spec = FINANCIAL_BY_NAME[name]
    changed = writable(access, spec, {}, values)
    row = spec.model(
        id=uuid7(),
        tenant_id=access.actor.tenant_id,
        company_id=access.context.company_id,
        created_by=access.actor.user_id,
        updated_by=access.actor.user_id,
        **values,
    )
    db.add(row)
    await db.flush()
    audit(db, access, spec, row, "create", changed)
    return row


async def change_row(
    db: AsyncSession, access: Access, name: str, row: Record, action: str, **values: Any
) -> None:
    spec = FINANCIAL_BY_NAME[name]
    before = values_of(row, spec)
    changed = writable(access, spec, before, before | values)
    for field, value in values.items():
        setattr(row, field, value)
    row.row_version += 1
    row.updated_by = access.actor.user_id
    await db.flush()
    audit(db, access, spec, row, action, changed)
