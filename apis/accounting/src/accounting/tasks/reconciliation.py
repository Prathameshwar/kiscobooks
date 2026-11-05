"""Compare posted party control accounts with dated subledger facts."""

import datetime as dt
from decimal import Decimal

from billing_platform.db.access import company_object
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import Money
from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import case, func, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.models.charges import ChargeAssessment
from accounting.models.fiscal import FiscalPeriod
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import Account
from accounting.models.subledger import OpeningBatch, OpenItem
from accounting.schemas.ledger import BalanceQuery
from accounting.schemas.subledger import Reconciliation
from accounting.tasks.ledger_reads import balance
from accounting.tasks.subledger_reads import active, remaining, require_inputs


async def account(db: AsyncSession, access: Access, query: BalanceQuery) -> Reconciliation:
    if query.account_id is None:
        raise ValidationFailedError("reconciliation requires a party control account")
    row = await company_object(db, Account, query.account_id, company_id=access.context.company_id)
    if row.kind != "PARTY":
        raise ValidationFailedError("reconciliation requires a debtor or creditor account")
    require_inputs(access)
    ledger = await balance(db, access, query)
    amount = remaining(query.as_of, base=query.basis == "BASE")
    positive = ((OpenItem.role == "CUSTOMER") & (OpenItem.direction == "DEBT")) | (
        (OpenItem.role == "SUPPLIER") & (OpenItem.direction == "CREDIT")
    )
    statement = select(
        type_coerce(func.coalesce(func.sum(case((positive, amount), else_=-amount)), 0), Money)
    ).where(
        OpenItem.company_id == row.company_id, OpenItem.account_id == row.id, active(query.as_of)
    )
    if query.basis == "ORIGINAL":
        statement = statement.where(OpenItem.currency == query.currency)
    subledger = await db.scalar(statement) or Decimal(0)
    return Reconciliation(
        account_id=row.id,
        as_of=query.as_of,
        currency=query.currency,
        ledger_balance=ledger.balance,
        subledger_balance=subledger,
        difference=ledger.balance - subledger,
    )


async def assert_reconciled(db: AsyncSession, access: Access, date: dt.date) -> None:
    # Keep both sides ORM-rooted so the platform applies tenant criteria in every
    # correlated aggregate. A raw UNION cannot be safely tenant-adapted.
    for base in (True, False):
        ledger_amount = JournalLine.base_amount if base else JournalLine.amount
        ledger_currency = JournalLine.base_currency if base else JournalLine.currency
        item_currency = OpenItem.base_currency if base else OpenItem.currency
        signed_ledger = case((JournalLine.side == "DEBIT", ledger_amount), else_=-ledger_amount)
        outstanding = remaining(date, base=base)
        positive = ((OpenItem.role == "CUSTOMER") & (OpenItem.direction == "DEBT")) | (
            (OpenItem.role == "SUPPLIER") & (OpenItem.direction == "CREDIT")
        )
        signed_item = case((positive, outstanding), else_=-outstanding)
        ledger_filters = (
            JournalLine.company_id == access.context.company_id,
            Journal.company_id == access.context.company_id,
            Journal.status == "POSTED",
            Journal.posting_date <= date,
            JournalLine.party_id.is_not(None),
        )
        item_filters = (OpenItem.company_id == access.context.company_id, active(date))
        items_total = (
            select(func.coalesce(func.sum(signed_item), 0))
            .where(
                *item_filters,
                OpenItem.account_id == JournalLine.account_id,
                item_currency == ledger_currency,
            )
            .correlate(JournalLine)
            .scalar_subquery()
        )
        ledger_total = (
            select(func.coalesce(func.sum(signed_ledger), 0))
            .join(Journal, Journal.id == JournalLine.journal_id)
            .where(
                *ledger_filters,
                JournalLine.account_id == OpenItem.account_id,
                ledger_currency == item_currency,
            )
            .correlate(OpenItem)
            .scalar_subquery()
        )
        ledger_mismatch = await db.scalar(
            select(JournalLine.account_id)
            .join(Journal, Journal.id == JournalLine.journal_id)
            .where(*ledger_filters)
            .group_by(JournalLine.account_id, ledger_currency)
            .having(func.sum(signed_ledger) != items_total)
            .limit(1)
        )
        item_mismatch = await db.scalar(
            select(OpenItem.account_id)
            .where(*item_filters)
            .group_by(OpenItem.account_id, item_currency)
            .having(func.sum(signed_item) != ledger_total)
            .limit(1)
        )
        if ledger_mismatch or item_mismatch:
            raise ConflictError("party control accounts do not reconcile to the subledger")


async def closing_checks(db: AsyncSession, access: Access, period: FiscalPeriod) -> None:
    from accounting.tasks.stock_reconciliation import closing_checks as stock_closing_checks

    await stock_closing_checks(db, period.company_id, period.start_date, period.end_date)
    # This is an invariant check, not a report; it does not expose any denied amounts.
    finance = access.context.finance
    if finance is not None and period.end_date >= finance.books_begin_date:
        opening = await db.scalar(
            select(OpeningBatch.id)
            .where(
                OpeningBatch.company_id == period.company_id,
                OpeningBatch.status == "FINALIZED",
            )
            .limit(1)
        )
        if opening is None:
            raise ConflictError("finalize opening balances before closing the books")
    for model, states in ((OpeningBatch, ["DRAFT"]), (ChargeAssessment, ["DRAFT", "APPROVED"])):
        pending = await db.scalar(
            select(model.id)
            .where(
                model.company_id == period.company_id,
                model.posting_date >= period.start_date,
                model.posting_date <= period.end_date,
                model.status.in_(states),
            )
            .limit(1)
        )
        if pending:
            raise ConflictError("period has pending openings or charge assessments")
    failed = await db.scalar(
        select(Outbox.id)
        .where(
            Outbox.tenant_id == access.actor.tenant_id,
            Outbox.payload["company_id"].as_string() == str(period.company_id),
            Outbox.published_at.is_(None),
            Outbox.attempt_count > 0,
        )
        .limit(1)
    )
    if failed:
        raise ConflictError("company has failed outbox deliveries requiring recovery")
    posted = select(Journal.id).where(
        Journal.company_id == period.company_id,
        Journal.posting_date <= period.end_date,
        Journal.status == "POSTED",
    )
    pending_authority = await db.scalar(
        select(Outbox.id)
        .where(
            Outbox.tenant_id == access.actor.tenant_id,
            Outbox.aggregate_id.in_(posted),
            Outbox.event_type == "accounting.company_posting.confirm",
            Outbox.published_at.is_(None),
        )
        .limit(1)
    )
    if pending_authority:
        raise ConflictError("posting confirmations must be delivered before closing")
    await assert_reconciled(db, access, period.end_date)
