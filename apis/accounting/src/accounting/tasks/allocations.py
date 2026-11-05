"""Serialized, reversible same-currency allocations and realized FX journals."""

import datetime as dt
import hashlib
import uuid
from decimal import Decimal
from typing import cast

from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import CommandResult
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.settlement import carrying_amount
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import Account
from accounting.models.subledger import Allocation, OpenItem
from accounting.schemas.subledger import AllocationCreate, AllocationReverse
from accounting.tasks.finance_records import change_row, create_row, require_fields
from accounting.tasks.financial_commands import (
    FinancialEffect,
    financial_command,
    financial_context,
)
from accounting.tasks.fiscal import posting_period, setup
from accounting.tasks.journal_posting import allocate_number
from accounting.tasks.subledger_reads import item_balance, require_inputs


async def latest_event(db: AsyncSession, item: OpenItem, date: dt.date) -> None:
    from accounting.tasks.charges import guard_history

    await guard_history(db, item.company_id, item.id, date)
    statement = select(func.max(Allocation.posting_date), func.max(Allocation.reversal_date)).where(
        Allocation.company_id == item.company_id,
        (Allocation.debt_item_id == item.id) | (Allocation.credit_item_id == item.id),
    )
    values = (await db.execute(statement)).one()
    if date < item.posting_date or any(value is not None and date < value for value in values):
        raise ConflictError("allocation cannot precede the item or its later allocation history")
    if item.reversal_date is not None:
        raise ConflictError("reversed items cannot be allocated")


async def realized_fx(
    db: AsyncSession,
    access: Access,
    allocation: Allocation,
    debt: OpenItem,
    credit: OpenItem,
    account_id: uuid.UUID,
    date: dt.date,
    *,
    reverse: bool = False,
) -> Journal:
    """Derive only from posted money whose Identity reservation already froze the configuration.

    The explicit authorization_journal_id links that ratchet proof. This operation adds no
    new feature and performs no remote call; the journal and allocation commit together.
    """
    config = await setup(db, access)
    period = await posting_period(db, access, date)
    credit_line = await company_object(
        db, JournalLine, credit.journal_line_id, company_id=credit.company_id
    )
    parent = await company_object(db, Journal, credit_line.journal_id, company_id=credit.company_id)
    if (
        parent.status != "POSTED"
        or parent.reservation_id is None
        or parent.base_currency != config.base_currency
    ):
        raise ConflictError("settlement posting authority is unavailable")
    needed = {"multi_currency"} if credit.currency != config.base_currency else set()
    if not needed <= set(parent.features) or not needed <= access.context.features:
        raise ConflictError("derived FX requires its posted currency authorization")
    offset = await company_object(db, Account, account_id, company_id=debt.company_id)
    require_fields(access, "account", {"kind", "status", "currency_mode"}, row=offset)
    if (
        offset.kind != "GENERAL"
        or (offset.status != "ACTIVE" and not reverse)
        or offset.currency_mode != "BASE"
    ):
        raise ValidationFailedError("realized FX requires an active base-currency general account")
    delta = allocation.credit_base_amount - allocation.debt_base_amount
    if reverse:
        delta = -delta
    if delta == 0:
        raise ConflictError("zero realized FX cannot create a journal")
    amount = abs(delta)
    party_debit = (delta > 0) == (debt.role == "CUSTOMER")
    number = await allocate_number(
        db, access, Journal(company_id=credit.company_id, kind="REALIZED_FX"), period.fiscal_year_id
    )
    row = cast(
        Journal,
        await create_row(
            db,
            access,
            "journal",
            kind="REALIZED_FX",
            status="POSTED",
            document_date=date,
            posting_date=date,
            description="Realized exchange difference" + (" reversal" if reverse else ""),
            base_currency=config.base_currency,
            total_debit=amount,
            total_credit=amount,
            source_system="accounting",
            source_type="allocation_reversal" if reverse else "allocation_fx",
            source_id=str(allocation.id),
            source_hash=hashlib.sha256(str(allocation.id).encode()).hexdigest(),
            number=number,
            fiscal_period_id=period.id,
            reversal_of_id=allocation.fx_journal_id if reverse else None,
            authorization_journal_id=parent.id,
            configuration_hash=financial_context(access).configuration_hash,
            features=sorted(needed),
            prepared_at=utcnow(),
            prepared_by=access.actor.user_id,
            prepared_version=1,
            reservation_id=parent.reservation_id,
            posted_at=utcnow(),
        ),
    )
    for sequence, party in ((1, True), (2, False)):
        await create_row(
            db,
            access,
            "journal_line",
            journal_id=row.id,
            sequence=sequence,
            component="FX" if party else "PRINCIPAL",
            account_id=debt.account_id if party else offset.id,
            side="DEBIT" if (party_debit if party else not party_debit) else "CREDIT",
            currency=debt.currency if party else config.base_currency,
            amount=Decimal(0) if party else amount,
            exchange_rate=Decimal(1),
            base_currency=config.base_currency,
            base_amount=amount,
            party_id=debt.party_id if party else None,
            role=debt.role if party else None,
            description="Realized exchange difference",
        )
    if offset.used_at is None:
        from accounting.resources import BY_NAME
        from accounting.tasks.access import writable
        from accounting.tasks.commands import audit, values_of

        spec = BY_NAME["account"]
        before = values_of(offset, spec)
        changed = writable(access, spec, before, before | {"used_at": row.posted_at})
        offset.used_at = row.posted_at
        offset.row_version += 1
        offset.updated_by = access.actor.user_id
        await db.flush()
        audit(db, access, spec, offset, "update", changed)
    from accounting.events.financial_contract import journal_posted

    await journal_posted(db, row)
    return row


async def create(
    factory: async_sessionmaker[AsyncSession], access: Access, body: AllocationCreate, key: str
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        return await create_in_transaction(db, access, body)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["allocation"],
        "create",
        body,
        key,
        mutate,
        permission="ledger.post_journal",
        status=201,
    )


async def reverse(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: AllocationReverse,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        return await reverse_in_transaction(db, access, object_id, body)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["allocation"],
        "reverse",
        body,
        key,
        mutate,
        permission="ledger.post_journal",
        object_id=object_id,
    )


async def create_in_transaction(
    db: AsyncSession, access: Access, body: AllocationCreate
) -> FinancialEffect:
    """Caller holds the company fence; allocations and realized FX commit together."""
    require_inputs(access)
    await posting_period(db, access, body.posting_date)
    debt = await company_object(
        db, OpenItem, body.debt_item_id, company_id=access.context.company_id
    )
    credit = await company_object(
        db, OpenItem, body.credit_item_id, company_id=access.context.company_id
    )
    if (
        debt.direction != "DEBT"
        or credit.direction != "CREDIT"
        or any(
            getattr(debt, name) != getattr(credit, name)
            for name in ("party_id", "role", "account_id", "currency", "base_currency")
        )
    ):
        raise ValidationFailedError(
            "allocation requires debt and credit for the same party role, account and currency"
        )
    await latest_event(db, debt, body.posting_date)
    await latest_event(db, credit, body.posting_date)
    debt_left = await item_balance(db, access, debt.id, body.posting_date)
    credit_left = await item_balance(db, access, credit.id, body.posting_date)
    debt_base = carrying_amount(
        debt.amount,
        debt.base_amount,
        debt_left.remaining,
        debt_left.base_remaining,
        body.amount,
    )
    credit_base = carrying_amount(
        credit.amount,
        credit.base_amount,
        credit_left.remaining,
        credit_left.base_remaining,
        body.amount,
    )
    if debt_base != credit_base and body.fx_account_id is None:
        raise ValidationFailedError(
            "a realized FX account is required for different carrying rates"
        )
    row = cast(
        Allocation,
        await create_row(
            db,
            access,
            "allocation",
            debt_item_id=debt.id,
            credit_item_id=credit.id,
            posting_date=body.posting_date,
            currency=debt.currency,
            amount=body.amount,
            base_currency=debt.base_currency,
            debt_base_amount=debt_base,
            credit_base_amount=credit_base,
            fx_journal_id=None,
            reversal_date=None,
            reversal_reason=None,
            fx_reversal_id=None,
        ),
    )
    if debt_base != credit_base and body.fx_account_id is not None:
        journal = await realized_fx(
            db, access, row, debt, credit, body.fx_account_id, body.posting_date
        )
        await change_row(db, access, "allocation", row, "update", fx_journal_id=journal.id)
    return FinancialEffect(row)


async def reverse_in_transaction(
    db: AsyncSession, access: Access, object_id: uuid.UUID, body: AllocationReverse
) -> FinancialEffect:
    """Reverse under the caller company fence, including any realized FX journal."""
    require_inputs(access)
    await posting_period(db, access, body.posting_date)
    row = await company_object(db, Allocation, object_id, company_id=access.context.company_id)
    if row.row_version != body.expected_version or row.reversal_date is not None:
        raise ConflictError("allocation version changed or is already reversed")
    debt = await company_object(db, OpenItem, row.debt_item_id, company_id=row.company_id)
    credit = await company_object(db, OpenItem, row.credit_item_id, company_id=row.company_id)
    await latest_event(db, debt, body.posting_date)
    await latest_event(db, credit, body.posting_date)
    fx_reversal_id = None
    if row.fx_journal_id:
        offset = await db.scalar(
            select(JournalLine).where(
                JournalLine.company_id == row.company_id,
                JournalLine.journal_id == row.fx_journal_id,
                JournalLine.sequence == 2,
            )
        )
        if offset is None:
            raise ConflictError("realized FX counterpart is missing")
        fx_reversal = await realized_fx(
            db, access, row, debt, credit, offset.account_id, body.posting_date, reverse=True
        )
        fx_reversal_id = fx_reversal.id
    await change_row(
        db,
        access,
        "allocation",
        row,
        "reverse",
        reversal_date=body.posting_date,
        reversal_reason=body.reason,
        fx_reversal_id=fx_reversal_id,
    )
    return FinancialEffect(row)
