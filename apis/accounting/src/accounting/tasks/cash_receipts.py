"""One daily cash control across legacy documents and ordinary vouchers."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.errors import ConflictError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import Account
from accounting.tasks.financial_commands import financial_context


async def check(
    db: AsyncSession,
    access: Access,
    posting_date: dt.date,
    amount: Decimal,
    parties: set[uuid.UUID],
    *,
    include_prepared: bool = False,
    exclude_journal: uuid.UUID | None = None,
) -> None:
    cap = financial_context(access).cash_receipt_limit
    if cap is None or amount == 0:
        return
    if amount > cap:
        raise ConflictError("cash receipt exceeds the company limit")
    company_id = access.context.company_id
    for party in parties:
        party_journals = select(JournalLine.journal_id).where(
            JournalLine.company_id == company_id, JournalLine.party_id == party
        )
        query = (
            select(func.coalesce(func.sum(JournalLine.base_amount), Decimal(0)))
            .join(Journal, Journal.id == JournalLine.journal_id)
            .join(Account, Account.id == JournalLine.account_id)
            .where(
                Journal.company_id == company_id,
                Journal.posting_date == posting_date,
                Journal.status.in_(("PREPARED", "POSTED") if include_prepared else ("POSTED",)),
                Journal.id.in_(party_journals),
                JournalLine.side == "DEBIT",
                Account.kind == "CASH",
            )
        )
        if exclude_journal is not None:
            query = query.where(Journal.id != exclude_journal)
        previous = await db.scalar(query) or Decimal(0)
        if previous + amount > cap:
            raise ConflictError("cash receipt exceeds the aggregate daily limit for this party")
