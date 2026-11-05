"""Native journal hooks for reviewed opening chunks; no independent money writer."""

from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.domain.financial_opening import opening_plan
from accounting.models.financial_opening import FinancialOpeningChunk
from accounting.models.ledger import Journal
from accounting.models.subledger import OpeningBatch
from accounting.tasks.finance_records import change_row
from accounting.tasks.financial_opening import chunks, require_account_identity, revision
from accounting.tasks.openings import preview


async def owner(
    db: AsyncSession, current: Any, journal: Journal
) -> tuple[OpeningBatch, FinancialOpeningChunk] | None:
    link = await db.scalar(
        select(FinancialOpeningChunk).where(
            FinancialOpeningChunk.company_id == journal.company_id,
            FinancialOpeningChunk.journal_id == journal.id,
        )
    )
    if link is None:
        return None
    batch = await company_object(db, OpeningBatch, link.batch_id, company_id=journal.company_id)
    return batch, link


async def before_post(db: AsyncSession, current: Any, journal: Journal) -> bool:
    result = await owner(db, current, journal)
    if result is None:
        return False
    batch, link = result
    rev = await revision(db, current, batch)
    if (
        batch.status != "DRAFT"
        or batch.payload.get("opening_correction")
        or rev.id != link.revision_id
    ):
        raise ConflictError("opening journal is not part of the current reviewed declaration")
    if journal.source_type != "financial_opening_chunk" or journal.source_id != str(link.id):
        raise ConflictError("opening journal source lineage differs")
    await require_account_identity(db, current, batch)
    body = opening_plan(link.payload)
    from accounting.domain.ledger import base_value
    from accounting.tasks.financial_commands import financial_context
    from accounting.tasks.journal_drafts import lines

    facts = financial_context(current)
    actual = await lines(db, batch.company_id, journal.id)
    from accounting.models.ledger import JournalLine
    from accounting.models.masters import Account

    changed_identity = await db.scalar(
        select(JournalLine.id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(
            JournalLine.company_id == batch.company_id,
            JournalLine.journal_id == journal.id,
            (JournalLine.party_id.is_distinct_from(Account.party_id))
            | (JournalLine.role.is_distinct_from(Account.party_role)),
        )
        .limit(1)
    )
    if changed_identity:
        raise ConflictError("native opening party snapshot differs from its declaration")
    if len(actual) != len(body.lines) or journal.posting_date != body.posting_date:
        raise ConflictError("native opening journal differs from its reviewed declaration")
    for stored, expected in zip(actual, body.lines, strict=True):
        value = expected.opening_base_amount or base_value(
            expected.amount,
            expected.currency,
            expected.exchange_rate,
            current.context.base_currency,
            facts.amount_precision,
            facts.rounding_mode,
        )
        if (
            stored.account_id,
            stored.side,
            stored.currency,
            stored.amount,
            stored.exchange_rate,
            stored.base_amount,
        ) != (
            expected.account_id,
            expected.side,
            expected.currency,
            expected.amount,
            expected.exchange_rate,
            value,
        ):
            raise ConflictError("native opening journal differs from its reviewed declaration")
    await preview(db, current, body)
    return True


async def after_post(db: AsyncSession, current: Any, journal: Journal) -> bool:
    result = await owner(db, current, journal)
    if result is None:
        return False
    from accounting.tasks.journal_drafts import lines
    from accounting.tasks.subledger_posting import make_items

    batch, link = result
    body = opening_plan(link.payload)
    for sequence, line in enumerate(await lines(db, journal.company_id, journal.id), 1):
        if line.party_id:
            parts = [
                bill.model_dump(mode="json")
                for bill in body.bills
                if bill.line_sequence == sequence
            ]
            await make_items(
                db,
                current,
                journal,
                line,
                parts,
                {"opening_batch_id": str(batch.id), "opening_revision_id": str(link.revision_id)},
            )
    # Accounting commit is durable; company completion remains an explicit reviewed command
    # after every child and its Identity confirmation is reconciled.
    await change_row(db, current, "opening_batch", batch, "update", payload=dict(batch.payload))
    return True


async def after_reversal(db: AsyncSession, current: Any, original: Journal) -> bool:
    result = await owner(db, current, original)
    if result is None:
        return False
    batch, _ = result
    links = await chunks(db, current, batch)
    ids = [link.journal_id for link in links if link.journal_id]
    reversed_ids = set(
        await db.scalars(
            select(Journal.reversal_of_id).where(
                Journal.company_id == batch.company_id,
                Journal.reversal_of_id.in_(ids),
                Journal.status == "POSTED",
            )
        )
    )
    journals = list(
        await db.scalars(
            select(Journal).where(Journal.company_id == batch.company_id, Journal.id.in_(ids))
        )
    )
    complete = all(row.status == "VOID" or row.id in reversed_ids for row in journals)
    await change_row(
        db,
        current,
        "opening_batch",
        batch,
        "reverse",
        status="REVERSED" if complete else "DRAFT",
        payload=batch.payload | {"opening_correction": True},
    )
    return True


async def reversal_guard(db: AsyncSession, current: Any, original: Journal) -> None:
    result = await owner(db, current, original)
    if result is None:
        return
    from accounting.models.ledger import JournalLine
    from accounting.models.subledger import Allocation, OpenItem

    batch, _ = result
    ids = [link.journal_id for link in await chunks(db, current, batch) if link.journal_id]
    item_ids = (
        select(OpenItem.id)
        .join(JournalLine, JournalLine.id == OpenItem.journal_line_id)
        .where(OpenItem.company_id == batch.company_id, JournalLine.journal_id.in_(ids))
    )
    if await db.scalar(
        select(Allocation.id)
        .where(
            Allocation.company_id == batch.company_id,
            ((Allocation.debt_item_id.in_(item_ids)) | (Allocation.credit_item_id.in_(item_ids))),
            Allocation.reversal_date.is_(None),
        )
        .limit(1)
    ):
        raise ConflictError(
            "reverse all dependent opening settlements before correcting the company declaration"
        )
    from accounting.models.charges import ChargeAssessment

    if await db.scalar(
        select(ChargeAssessment.id)
        .where(
            ChargeAssessment.company_id == batch.company_id,
            ChargeAssessment.item_id.in_(item_ids),
            ChargeAssessment.status.in_(["DRAFT", "APPROVED", "POSTED"]),
        )
        .limit(1)
    ):
        raise ConflictError("resolve all dependent opening charges before correction")
    from accounting.models.stock import StockOpeningBridge
    from accounting.tasks.stock_opening_claims import claimed

    bridge_lines = list(
        await db.scalars(
            select(StockOpeningBridge.journal_line_id)
            .distinct()
            .where(
                StockOpeningBridge.company_id == batch.company_id,
                StockOpeningBridge.journal_line_id.in_(
                    select(JournalLine.id).where(
                        JournalLine.company_id == batch.company_id, JournalLine.journal_id.in_(ids)
                    )
                ),
            )
        )
    )
    for line_id in bridge_lines:
        if await db.scalar(claimed(batch.company_id, line_id)):
            raise ConflictError(
                "reverse linked physical stock openings before correcting financial openings"
            )
    from accounting.tasks.banking import legacy_reversal

    journals = list(
        await db.scalars(
            select(Journal).where(Journal.company_id == batch.company_id, Journal.id.in_(ids))
        )
    )
    for journal in journals:
        await legacy_reversal(db, current, journal)
    from accounting.models.bank_reconciliation import BankReconciliationSession
    from accounting.models.masters import Account

    bank_ids = (
        select(JournalLine.account_id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(
            JournalLine.company_id == batch.company_id,
            JournalLine.journal_id.in_(ids),
            Account.kind == "BANK",
        )
    )
    if await db.scalar(
        select(BankReconciliationSession.id)
        .where(
            BankReconciliationSession.company_id == batch.company_id,
            BankReconciliationSession.account_id.in_(bank_ids),
            BankReconciliationSession.status == "FINALIZED",
            BankReconciliationSession.period_to >= batch.posting_date,
        )
        .limit(1)
    ):
        raise ConflictError(
            "amend finalized bank reconciliations before correcting company openings"
        )
