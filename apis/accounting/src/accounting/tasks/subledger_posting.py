"""Subledger effects attached atomically to the journal posting transaction."""

import datetime as dt
from decimal import Decimal, localcontext
from typing import Any, cast

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.money import quantize_storage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.models.ledger import Journal, JournalLine
from accounting.models.subledger import Allocation, OpeningBatch, OpenItem, SourceDocument
from accounting.schemas.subledger import OpeningCreate, SourceCreate
from accounting.tasks.finance_records import change_row, create_row, require_fields
from accounting.tasks.journal_drafts import lines
from accounting.tasks.openings import preview, require_opening_revision_window
from accounting.tasks.party_documents import enforce_holds, party_account, policy_at


async def validate_reversal(db: AsyncSession, access: Access, original: Journal) -> None:
    from accounting.tasks.invoice_credit import reversal_guard as tax_reversal_guard

    await tax_reversal_guard(db, original)
    from accounting.tasks.banking import legacy_reversal

    await legacy_reversal(db, access, original)
    owned_allocations = set()
    if original.kind == "VOUCHER":
        from accounting.models.voucher_money import VoucherMoneyAllocation, VoucherMoneyIntent

        intent = await db.scalar(
            select(VoucherMoneyIntent).where(
                VoucherMoneyIntent.company_id == original.company_id,
                VoucherMoneyIntent.journal_id == original.id,
            )
        )
        if intent is None or db.info.get("voucher_money_reversal") != intent.execution_id:
            raise ConflictError("voucher reversal requires its execution protocol")
        owned_allocations = set(
            await db.scalars(
                select(VoucherMoneyAllocation.allocation_id).where(
                    VoucherMoneyAllocation.company_id == original.company_id,
                    VoucherMoneyAllocation.intent_id == intent.id,
                )
            )
        )
    from accounting.tasks.charges import reversal_guard

    await reversal_guard(db, access, original)
    line_ids = select(JournalLine.id).where(
        JournalLine.company_id == original.company_id, JournalLine.journal_id == original.id
    )
    item_ids = select(OpenItem.id).where(
        OpenItem.company_id == original.company_id, OpenItem.journal_line_id.in_(line_ids)
    )
    from accounting.models.charges import ChargeAssessment

    charged = await db.scalar(
        select(ChargeAssessment.id)
        .where(
            ChargeAssessment.company_id == original.company_id,
            ChargeAssessment.item_id.in_(item_ids),
            ChargeAssessment.status.in_(["DRAFT", "APPROVED", "POSTED"]),
        )
        .limit(1)
    )
    if charged:
        raise ConflictError("resolve dependent charges before reversing this document")
    allocated = await db.scalar(
        select(Allocation.id)
        .where(
            Allocation.company_id == original.company_id,
            ((Allocation.debt_item_id.in_(item_ids)) | (Allocation.credit_item_id.in_(item_ids))),
            Allocation.reversal_date.is_(None),
            Allocation.id.not_in(owned_allocations),
        )
        .limit(1)
    )
    if allocated:
        raise ConflictError("reverse dependent allocations before reversing this document")
    if original.kind == "OPENING":
        from accounting.tasks.financial_opening_posting import (
            reversal_guard as workspace_reversal_guard,
        )

        await workspace_reversal_guard(db, access, original)
        await require_opening_revision_window(db, access, original.posting_date)
        dependent = await db.scalar(
            select(Journal.id)
            .where(
                Journal.company_id == original.company_id,
                Journal.status.in_(["PREPARED", "POSTED"]),
                Journal.kind.not_in(["OPENING", "REVERSAL"]),
            )
            .limit(1)
        )
        if dependent:
            raise ConflictError("opening correction is blocked after trading has started")


async def before_post(db: AsyncSession, access: Access, journal: Journal) -> None:
    if journal.kind == "OPENING":
        access.actor.require_scope(
            "accounting.finance.manage", target=ScopePath(company_id=journal.company_id)
        )
        # Shared by legacy and workspace openings at native prepare and commit.
        # Remote authorization never freezes the current opening revision window.
        await require_opening_revision_window(db, access, journal.posting_date)
        from accounting.tasks.financial_opening_posting import before_post as workspace_before_post

        if await workspace_before_post(db, access, journal):
            return
        batch = await db.scalar(
            select(OpeningBatch).where(
                OpeningBatch.company_id == journal.company_id, OpeningBatch.journal_id == journal.id
            )
        )
        if batch is None or batch.status != "DRAFT":
            raise ConflictError("opening journal has no current opening batch")
        from accounting.tasks.master_opening_posting import before_post as master_before_post

        await master_before_post(db, access, journal, batch)
        await preview(
            db,
            access,
            OpeningCreate.model_validate(batch.payload),
            master_opening_id=batch.id if journal.source_system == "master-creation" else None,
        )
        return
    if journal.kind == "REVERSAL":
        if journal.reversal_of_id is None:
            raise ConflictError("reversal requires its original journal")
        original = await company_object(
            db, Journal, journal.reversal_of_id, company_id=journal.company_id
        )
        await validate_reversal(db, access, original)
        return
    finalized = await db.scalar(
        select(OpeningBatch.id)
        .where(OpeningBatch.company_id == journal.company_id, OpeningBatch.status == "FINALIZED")
        .limit(1)
    )
    if finalized is None:
        raise ConflictError("finalize opening balances before ordinary posting")
    if journal.kind == "VOUCHER":
        from accounting.tasks.voucher_money_effects import before_post as money_before_post

        await money_before_post(db, access, journal)
        return
    if journal.kind == "TAX_ACTION":
        from accounting.tasks.invoice_credit import before_post as tax_before_post

        await tax_before_post(db, access, journal)
        return
    if journal.kind == "CHARGE":
        from accounting.tasks.charges import before_post as charge_before_post

        await charge_before_post(db, access, journal)
        return
    from accounting.tasks.voucher_tax import verify

    if journal.kind == "MANUAL":
        await verify(db, access, journal)
        return
    source = await db.scalar(
        select(SourceDocument).where(
            SourceDocument.company_id == journal.company_id, SourceDocument.journal_id == journal.id
        )
    )
    if source is None or source.status != "DRAFT":
        raise ConflictError("party journal requires its source workflow")
    require_fields(
        access,
        "source_document",
        {"payload", "amount", "currency", "account_id", "party_id", "role"},
    )
    account = await party_account(db, access, source.account_id)
    policy = await policy_at(db, access, account, journal.posting_date)
    enforce_holds(policy, source.kind)
    from accounting.tasks.credit import source_control

    await source_control(db, access, source)
    # Recheck the immutable request against current company controls at posting time.
    body = SourceCreate.model_validate(source.payload["request"])
    from accounting.models.masters import Account

    offset = await company_object(
        db, Account, body.counterpart_account_id, company_id=journal.company_id
    )
    if source.kind == "RECEIPT" and offset.kind == "CASH":
        from accounting.tasks.cash_receipts import check

        await check(
            db,
            access,
            journal.posting_date,
            journal.total_debit,
            {source.party_id},
            exclude_journal=journal.id,
        )
    await verify(db, access, journal)


async def make_items(
    db: AsyncSession,
    access: Access,
    journal: Journal,
    line: JournalLine,
    parts: list[dict[str, Any]],
    terms: dict[str, Any],
) -> None:
    if line.party_id is None or line.role is None:
        raise ConflictError("open item requires a debtor or creditor line")
    remaining = line.base_amount
    with localcontext() as context:
        context.prec = 48
        for index, part in enumerate(parts):
            amount = Decimal(part["amount"])
            base = (
                Decimal(part["base_amount"])
                if part.get("base_amount") is not None
                else (
                    remaining
                    if index == len(parts) - 1
                    else quantize_storage(line.base_amount * amount / line.amount)
                )
            )
            remaining -= base
            if base <= 0:
                raise ConflictError("installment base amount rounds to zero")
            await create_row(
                db,
                access,
                "open_item",
                journal_line_id=line.id,
                sequence=index + 1,
                account_id=line.account_id,
                party_id=line.party_id,
                role=line.role,
                direction="DEBT"
                if ((line.role == "CUSTOMER") == (line.side == "DEBIT"))
                else "CREDIT",
                reference=part["reference"],
                currency=line.currency,
                amount=amount,
                base_currency=line.base_currency,
                base_amount=base,
                document_date=dt.date.fromisoformat(part["document_date"])
                if part.get("document_date")
                else None,
                posting_date=journal.posting_date,
                due_date=dt.date.fromisoformat(part["due_date"]) if part.get("due_date") else None,
                terms=terms
                | (
                    {"tracking": "ON_ACCOUNT", "history_unknown": True}
                    if part.get("document_kind") == "ON_ACCOUNT"
                    else {}
                )
                | {
                    key: part[key]
                    for key in ("source_key", "document_kind", "original_amount")
                    if part.get(key) is not None
                },
                reversal_journal_id=None,
                reversal_date=None,
            )


async def after_post(db: AsyncSession, access: Access, journal: Journal) -> None:
    if journal.kind == "TAX_ACTION":
        from accounting.tasks.invoice_credit import after_post as tax_after_post

        await tax_after_post(db, access, journal)
        return
    if journal.kind == "VOUCHER":
        from accounting.tasks.voucher_money_effects import after_post as money_after_post

        await money_after_post(db, access, journal)
        return
    if journal.kind == "CHARGE":
        from accounting.tasks.charges import after_post as charge_after_post

        await charge_after_post(db, access, journal)
        return
    if journal.kind == "MANUAL":
        return
    if journal.kind == "REVERSAL":
        if journal.reversal_of_id is None:
            raise ConflictError("reversal requires its original journal")
        original = await company_object(
            db, Journal, journal.reversal_of_id, company_id=journal.company_id
        )
        original_lines = select(JournalLine.id).where(
            JournalLine.company_id == journal.company_id, JournalLine.journal_id == original.id
        )
        items = list(
            await db.scalars(
                select(OpenItem)
                .where(
                    OpenItem.company_id == journal.company_id,
                    OpenItem.journal_line_id.in_(original_lines),
                )
                .limit(1001)
            )
        )
        if len(items) > 1000:
            raise ConflictError("document exceeds supported open item capacity")
        for item in items:
            latest = await db.scalar(
                select(Allocation.posting_date)
                .where(
                    Allocation.company_id == journal.company_id,
                    (Allocation.debt_item_id == item.id) | (Allocation.credit_item_id == item.id),
                )
                .order_by(Allocation.posting_date.desc())
                .limit(1)
            )
            last_reversal = await db.scalar(
                select(Allocation.reversal_date)
                .where(
                    Allocation.company_id == journal.company_id,
                    (Allocation.debt_item_id == item.id) | (Allocation.credit_item_id == item.id),
                )
                .order_by(Allocation.reversal_date.desc())
                .limit(1)
            )
            if any(
                date is not None and date > journal.posting_date for date in (latest, last_reversal)
            ):
                raise ConflictError("document reversal cannot precede allocation history")
            await change_row(
                db,
                access,
                "open_item",
                item,
                "reverse",
                reversal_journal_id=journal.id,
                reversal_date=journal.posting_date,
            )
        from accounting.tasks.charges import after_reversal

        await after_reversal(db, access, original)
        from accounting.tasks.banking import legacy_reversal

        await legacy_reversal(db, access, original, journal)
        from accounting.tasks.financial_opening_posting import (
            after_reversal as workspace_after_reversal,
        )

        workspace_reversed = await workspace_after_reversal(db, access, original)
        for model, name in ((OpeningBatch, "opening_batch"), (SourceDocument, "source_document")):
            if model is OpeningBatch and workspace_reversed:
                continue
            row = await db.scalar(
                select(model).where(
                    model.company_id == journal.company_id, model.journal_id == original.id
                )
            )
            if row:
                await change_row(db, access, name, row, "reverse", status="REVERSED")
                if isinstance(row, OpeningBatch):
                    from accounting.tasks.master_opening_posting import record_outcome

                    await record_outcome(db, access, row, is_reversal=True)
        return
    stored = await lines(db, journal.company_id, journal.id)
    if journal.kind == "OPENING":
        from accounting.tasks.financial_opening_posting import after_post as workspace_after_post

        if await workspace_after_post(db, access, journal):
            return
        batch = await db.scalar(
            select(OpeningBatch).where(
                OpeningBatch.company_id == journal.company_id, OpeningBatch.journal_id == journal.id
            )
        )
        if batch is None:
            raise ConflictError("opening batch missing")
        body = OpeningCreate.model_validate(batch.payload)
        for sequence, line in enumerate(stored, 1):
            if line.party_id:
                parts = [
                    bill.model_dump(mode="json")
                    for bill in body.bills
                    if bill.line_sequence == sequence
                ]
                await make_items(
                    db, access, journal, line, parts, {"opening_batch_id": str(batch.id)}
                )
        await change_row(
            db,
            access,
            "opening_batch",
            batch,
            "finalize",
            status="FINALIZED",
            finalized_at=utcnow(),
        )
        from accounting.tasks.master_opening_posting import record_outcome

        await record_outcome(db, access, batch)
        return
    source = await db.scalar(
        select(SourceDocument).where(
            SourceDocument.company_id == journal.company_id, SourceDocument.journal_id == journal.id
        )
    )
    if source is None:
        raise ConflictError("party source missing")
    from accounting.tasks.credit import source_control

    await source_control(db, access, source, consume=True)
    parts = [
        part
        | {
            "reference": source.reference
            + (f"/{part['sequence']}" if len(source.payload["installments"]) > 1 else ""),
            "document_date": journal.document_date.isoformat(),
        }
        for part in source.payload["installments"]
    ]
    if any(len(part["reference"]) > 120 for part in parts):
        raise ConflictError("installment reference exceeds maximum length")
    await make_items(
        db, access, journal, stored[0], parts, cast(dict[str, Any], source.payload["terms"])
    )
    await change_row(db, access, "source_document", source, "post", status="POSTED")
