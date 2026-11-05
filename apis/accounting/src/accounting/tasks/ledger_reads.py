"""Posted-only as-of balances with protection on every financial input."""

from __future__ import annotations

from decimal import Decimal

from billing_platform.db.access import company_object
from billing_platform.db.types import Money
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from sqlalchemy import case, func, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import Account, Party
from accounting.schemas.ledger import Balance, BalanceQuery
from accounting.tasks.access import authorize, readable


async def balance(db: AsyncSession, access: Access, query: BalanceQuery) -> Balance:
    required = {
        "journal": {"status", "posting_date", "base_currency"},
        "journal_line": {
            "account_id",
            "party_id",
            "side",
            "currency",
            "amount",
            "base_amount",
            "base_currency",
        },
    }
    for name, fields in required.items():
        spec = FINANCIAL_BY_NAME[name]
        authorize(access, spec, "read")
        if not fields <= readable(access, spec):
            raise PermissionDeniedError("balance inputs are not readable")
    if query.account_id:
        await company_object(db, Account, query.account_id, company_id=access.context.company_id)
    if query.party_id:
        await company_object(db, Party, query.party_id, company_id=access.context.company_id)
    if query.basis == "BASE" and query.currency != access.context.base_currency:
        raise ValidationFailedError("base balance requires the company base currency")
    amount = JournalLine.base_amount if query.basis == "BASE" else JournalLine.amount
    debit = type_coerce(
        func.coalesce(
            func.sum(case((JournalLine.side == "DEBIT", amount), else_=Decimal(0))), Decimal(0)
        ),
        Money(),
    )
    credit = type_coerce(
        func.coalesce(
            func.sum(case((JournalLine.side == "CREDIT", amount), else_=Decimal(0))), Decimal(0)
        ),
        Money(),
    )
    statement = (
        select(debit, credit)
        .join(Journal, Journal.id == JournalLine.journal_id)
        .where(
            JournalLine.company_id == access.context.company_id,
            Journal.company_id == access.context.company_id,
            Journal.status == "POSTED",
            Journal.posting_date <= query.as_of,
        )
    )
    statement = (
        statement.where(JournalLine.base_currency == query.currency)
        if query.basis == "BASE"
        else statement.where(JournalLine.currency == query.currency)
    )
    if query.account_id:
        statement = statement.where(JournalLine.account_id == query.account_id)
    if query.party_id:
        statement = statement.where(JournalLine.party_id == query.party_id)
    row = (await db.execute(statement)).one()
    return Balance(
        as_of=query.as_of,
        currency=query.currency,
        debit=row[0],
        credit=row[1],
        balance=row[0] - row[1],
    )
