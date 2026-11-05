"""Applicable company ledgers inside the existing authorized books transaction."""

from __future__ import annotations

import datetime as dt

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.models import masters as m
from accounting.resources import BY_NAME
from accounting.schemas.setup import TemplateSelection
from accounting.seeds.default_accounts import DefaultAccounts, applicable_accounts
from accounting.tasks.access import writable
from accounting.tasks.commands import audit
from accounting.tasks.templates import bootstrap_conflicts, install_content, resolve_account
from accounting.tasks.validation import validate
from accounting.tasks.voucher_tax import utgst_states


async def provision(db: AsyncSession, access: Access, books_begin: dt.date) -> None:
    packs = applicable_accounts(
        access.context.registrations,
        access.context.features,
        books_begin,
        utcnow().date(),
        utgst_states(),
    )
    selection = TemplateSelection(business_accounts=False)
    # Check every pack before writing any of them. Field denies still roll back the transaction.
    for pack in packs:
        if await bootstrap_conflicts(db, access, selection, defaults=pack):
            raise ConflictError(
                "company default accounts conflict with existing masters; review setup"
            )
    for pack in packs:
        await install_content(db, access, selection, defaults=pack)
        await db.flush()
        await map_defaults(db, access, pack)


async def map_defaults(db: AsyncSession, access: Access, pack: DefaultAccounts) -> None:
    """Fill absent mapping purposes; never overwrite or supersede an operator's mapping."""
    company = access.context.company_id
    for code, purpose in pack.mappings.items():
        profile = pack.profiles.get(code, {})
        registration = profile.get("company_registration_id")
        if await db.scalar(
            select(m.AccountPostingMapping.id)
            .where(
                m.AccountPostingMapping.company_id == company,
                m.AccountPostingMapping.purpose == purpose,
                m.AccountPostingMapping.company_registration_id == registration,
                m.AccountPostingMapping.currency == access.context.base_currency,
            )
            .limit(1)
        ):
            continue
        definition = next(row for row in pack.accounts if row[0] == code)
        group = await db.scalar(
            select(m.AccountGroup).where(
                m.AccountGroup.company_id == company,
                m.AccountGroup.system_key == "group." + definition[2],
            )
        )
        account = await resolve_account(
            db,
            access,
            TemplateSelection(business_accounts=False),
            code,
            group,
            definition[3],
            defaults=pack,
        )
        if account is None:
            raise ConflictError("company default account is unavailable")
        values = {
            "purpose": purpose,
            "account_id": account.id,
            "company_registration_id": registration,
            "currency": access.context.base_currency,
            "valid_from": pack.valid_from,
            "valid_to": pack.valid_to,
        }
        spec = BY_NAME["account_posting_mapping"]
        changed = writable(access, spec, {}, values)
        await validate(db, access, spec, values)
        row = m.AccountPostingMapping(
            id=uuid7(),
            tenant_id=access.actor.tenant_id,
            company_id=company,
            created_by=access.actor.user_id,
            updated_by=access.actor.user_id,
            row_version=1,
            **values,
        )
        db.add(row)
        await db.flush()
        audit(db, access, spec, row, "create", changed)
