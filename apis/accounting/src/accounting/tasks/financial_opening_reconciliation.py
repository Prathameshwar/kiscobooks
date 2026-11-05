"""Reconcile frozen declaration, native journal lines and original bill carrying values."""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.access import company_object
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.domain.financial_opening import opening_plan
from accounting.domain.ledger import base_value
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import Account, AccountingSetup
from accounting.models.subledger import OpeningBatch, OpenItem
from accounting.schemas.financial_opening import OpeningReconciliation
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.financial_opening import chunks, require_read, revision
from accounting.tasks.openings import opening_window_blockers
from accounting.tasks.stock_opening_control import pending


async def reconcile(db: AsyncSession, current: Any, identity: uuid.UUID) -> OpeningReconciliation:
    require_read(current)
    # Services use READ COMMITTED. Hold the same company fence as all money and
    # setup writers so a reconciliation cannot mix pre/post-correction facts.
    # This shared lock changes neither setup generation nor any business row.
    await db.scalar(
        select(AccountingSetup.id)
        .where(AccountingSetup.company_id == current.context.company_id)
        .with_for_update(read=True)
    )
    batch = await company_object(db, OpeningBatch, identity, company_id=current.context.company_id)
    rev = await revision(db, current, batch)
    links = await chunks(db, current, batch)
    ids = [link.journal_id for link in links if link.journal_id]
    journals = {
        row.id: row
        for row in await db.scalars(
            select(Journal).where(Journal.company_id == batch.company_id, Journal.id.in_(ids))
        )
    }
    reversed_ids = set(
        await db.scalars(
            select(Journal.reversal_of_id).where(
                Journal.company_id == batch.company_id,
                Journal.reversal_of_id.in_(ids),
                Journal.status == "POSTED",
            )
        )
    )
    native = list(
        await db.scalars(
            select(JournalLine)
            .where(JournalLine.company_id == batch.company_id, JournalLine.journal_id.in_(ids))
            .order_by(JournalLine.journal_id, JournalLine.sequence)
            .limit(202001)
        )
    )
    line_ids = [line.id for line in native]
    items = list(
        await db.scalars(
            select(OpenItem)
            .where(
                OpenItem.company_id == batch.company_id,
                OpenItem.journal_line_id.in_(line_ids),
                OpenItem.reversal_date.is_(None),
            )
            .limit(10001)
        )
    )
    by_line: dict[uuid.UUID, list[OpenItem]] = {}
    for item in items:
        by_line.setdefault(item.journal_line_id, []).append(item)
    by_journal: dict[uuid.UUID, list[JournalLine]] = {}
    for line in native:
        by_journal.setdefault(line.journal_id, []).append(line)
    debit = credit = clearing_balance = Decimal(0)
    clearing_id = rev.header["declaration"].get("clearing_account_id")
    bank_debit = bank_credit = Decimal(0)
    bank_ids = set(
        await db.scalars(
            select(Account.id).where(
                Account.company_id == batch.company_id,
                Account.kind == "BANK",
                Account.id.in_({line.account_id for line in native}),
            )
        )
    )
    complete = bool(links) and len(journals) == len(links)
    gl_matches = party_matches = True
    facts = financial_context(current)
    for link in links:
        journal = journals.get(link.journal_id) if link.journal_id else None
        plan = opening_plan(link.payload)
        if journal is None or journal.status != "POSTED" or journal.id in reversed_ids:
            complete = False
            continue
        actual = by_journal.get(journal.id, [])
        if journal.posting_date != plan.posting_date or len(actual) != len(plan.lines):
            gl_matches = False
        for sequence, (line, expected) in enumerate(zip(actual, plan.lines, strict=False), 1):
            value = expected.opening_base_amount or base_value(
                expected.amount,
                expected.currency,
                expected.exchange_rate,
                current.context.base_currency,
                facts.amount_precision,
                facts.rounding_mode,
            )
            if (line.account_id, line.side, line.currency, line.amount, line.base_amount) != (
                expected.account_id,
                expected.side,
                expected.currency,
                expected.amount,
                value,
            ):
                gl_matches = False
            if clearing_id and str(line.account_id) == clearing_id:
                clearing_balance += line.base_amount if line.side == "DEBIT" else -line.base_amount
            elif line.side == "DEBIT":
                debit += line.base_amount
                if line.account_id in bank_ids:
                    bank_debit += line.base_amount
            else:
                credit += line.base_amount
                if line.account_id in bank_ids:
                    bank_credit += line.base_amount
            parts = by_line.get(line.id, [])
            bills = [bill for bill in plan.bills if bill.line_sequence == sequence]
            if len(parts) != len(bills):
                party_matches = False
            if line.party_id:
                debt = (line.role == "CUSTOMER") == (line.side == "DEBIT")
                if (
                    sum((part.amount for part in parts), Decimal(0)) != line.amount
                    or sum((part.base_amount for part in parts), Decimal(0)) != line.base_amount
                ):
                    party_matches = False
                for part, bill in zip(
                    sorted(parts, key=lambda item: item.sequence), bills, strict=False
                ):
                    if (
                        part.account_id,
                        part.party_id,
                        part.role,
                        part.direction,
                        part.currency,
                        part.reference,
                        part.amount,
                        part.document_date,
                        part.due_date,
                        part.posting_date,
                    ) != (
                        line.account_id,
                        line.party_id,
                        line.role,
                        "DEBT" if debt else "CREDIT",
                        line.currency,
                        bill.reference,
                        bill.amount,
                        bill.document_date,
                        bill.due_date,
                        plan.posting_date,
                    ) or (bill.base_amount is not None and bill.base_amount != part.base_amount):
                        party_matches = False
            elif parts or bills:
                party_matches = False
    expected_total = Decimal(rev.header["total_debit"])
    gl_matches = complete and gl_matches and debit == credit == expected_total
    party_matches = complete and party_matches and len(items) == rev.header["document_count"]
    unconfirmed = await pending(db, batch.company_id)
    blockers = await opening_window_blockers(db, batch.company_id, batch.posting_date)
    if not complete:
        blockers.append("OPENING_JOURNALS_NOT_POSTED")
    if clearing_balance:
        blockers.append("MIGRATION_CLEARING_NOT_ZERO")
    if not gl_matches:
        blockers.append("DECLARATION_GL_DIFFERENCE")
    if not party_matches:
        blockers.append("PARTY_OPEN_ITEM_DIFFERENCE")
    if unconfirmed:
        blockers.append("NATIVE_CONFIRMATION_PENDING")
    if batch.payload.get("opening_correction") or batch.status not in {"DRAFT", "FINALIZED"}:
        blockers.append("OPENING_NOT_CURRENT")
    header = rev.header["declaration"]
    return OpeningReconciliation(
        batch_id=batch.id,
        revision_id=rev.id,
        posting_date=batch.posting_date,
        covered_through=header["covered_through"],
        coverage_mode=header["coverage_mode"],
        currency=header["currency"],
        expected_debit=str(expected_total),
        expected_credit=str(expected_total),
        posted_debit=str(debit),
        posted_credit=str(credit),
        declared_documents=rev.header["document_count"],
        posted_documents=len(items),
        gl_matches=gl_matches,
        party_items_match=party_matches,
        confirmation_pending=unconfirmed,
        ready_to_finalize=not blockers and batch.status == "DRAFT",
        blockers=blockers,
        clearing_balance=str(clearing_balance),
        clearing_account_id=clearing_id,
        bank_gl_debit=str(bank_debit),
        bank_gl_credit=str(bank_credit),
        bank_opening_items_path=f"/v1/companies/{batch.company_id}/bank-reconciliation/opening-items",
        stock_opening_control_path=f"/v1/companies/{batch.company_id}/stock/openings/readiness",
    )
