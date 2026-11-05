"""Resolve and preserve classifications under the existing company mutation lock."""

from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.domain.master_metadata import GROUP_CLASSIFICATION, group_metadata
from accounting.models import masters as m


async def normalize_group(
    db: AsyncSession, access: Access, values: dict[str, Any], *, system_key: str | None = None
) -> dict[str, Any]:
    company = access.context.company_id
    head = await company_object(db, m.AccountHead, values["head_id"], company_id=company)
    parent = None
    if values.get("parent_id") is not None:
        row = await company_object(db, m.AccountGroup, values["parent_id"], company_id=company)
        parent = {"affects_gross_profit": row.affects_gross_profit}
    return values | group_metadata(values, head.nature, parent, system_key=system_key)


async def guard_group_change(
    db: AsyncSession, row: m.AccountGroup, values: dict[str, Any], changed: set[str]
) -> None:
    if row.is_primary and "parent_id" in changed:
        raise ConflictError("primary groups cannot be reparented through ordinary updates")
    if not changed & GROUP_CLASSIFICATION:
        return
    child = await db.scalar(
        select(m.AccountGroup.id)
        .where(
            m.AccountGroup.company_id == row.company_id,
            m.AccountGroup.parent_id == row.id,
            (m.AccountGroup.head_id != values["head_id"])
            | (m.AccountGroup.affects_gross_profit != values["affects_gross_profit"]),
        )
        .limit(1)
    )
    if child is not None:
        raise ConflictError("group classification would invalidate existing descendants")
    descendants = select(m.AccountGroupClosure.descendant_id).where(
        m.AccountGroupClosure.company_id == row.company_id,
        m.AccountGroupClosure.ancestor_id == row.id,
    )
    account = await db.scalar(
        select(m.Account.id)
        .where(
            m.Account.company_id == row.company_id,
            m.Account.group_id.in_(descendants),
            (m.Account.used_at.is_not(None)) | bool(changed - {"parent_id", "is_primary"}),
        )
        .limit(1)
    )
    if account is not None:
        raise ConflictError("group classification is referenced by existing accounts")
