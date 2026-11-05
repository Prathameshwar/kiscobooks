"""Balanced opening imports and once-only finalization at books begin date."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import cast

from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import CommandResult
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.fiscal import FiscalPeriod
from accounting.models.ledger import Journal
from accounting.models.subledger import OpeningBatch
from accounting.schemas.ledger import JournalCreate
from accounting.schemas.masters import ExpectedVersion
from accounting.schemas.subledger import OpeningCreate, OpeningPreview, OpeningReopen
from accounting.tasks.finance_records import change_row, create_row, require_fields
from accounting.tasks.financial_commands import (
    FinancialEffect,
    financial_command,
    financial_context,
)
from accounting.tasks.fiscal import posting_period, setup
from accounting.tasks.journal_drafts import (
    create_in_transaction,
    require_preview_fields,
    validate_lines,
)


async def require_opening_revision_window(
    db: AsyncSession, access: Access, posting_date: dt.date
) -> None:
    """Changing first-year opening must not invalidate a later closed period."""
    await posting_period(db, access, posting_date)
    closed = await db.scalar(
        select(FiscalPeriod.id)
        .where(
            FiscalPeriod.company_id == access.context.company_id,
            FiscalPeriod.end_date >= posting_date,
            FiscalPeriod.status.in_(["CLOSED", "LOCKED"]),
        )
        .limit(1)
    )
    if closed is not None:
        raise ConflictError("later closed or locked books prevent opening correction")


async def opening_window_blockers(
    db: AsyncSession, company_id: uuid.UUID, posting_date: dt.date
) -> list[str]:
    """Read-only opening readiness; command authorization remains in posting_period."""
    periods = list(
        await db.scalars(
            select(FiscalPeriod.status)
            .where(
                FiscalPeriod.company_id == company_id,
                FiscalPeriod.start_date <= posting_date,
                FiscalPeriod.end_date >= posting_date,
            )
            .limit(2)
        )
    )
    blockers = [] if periods == ["OPEN"] else ["BOOKS_BEGIN_PERIOD_NOT_OPEN"]
    if await db.scalar(
        select(FiscalPeriod.id)
        .where(
            FiscalPeriod.company_id == company_id,
            FiscalPeriod.end_date >= posting_date,
            FiscalPeriod.status.in_(["CLOSED", "LOCKED"]),
        )
        .limit(1)
    ):
        blockers.append("LATER_BOOKS_CLOSED")
    return blockers


async def preview(
    db: AsyncSession,
    access: Access,
    body: OpeningCreate,
    *,
    master_opening_id: uuid.UUID | None = None,
) -> OpeningPreview:
    require_fields(access, "opening_batch", {"payload", "posting_date"})
    require_preview_fields(access)
    facts = financial_context(access)
    await setup(db, access)
    if body.posting_date != facts.books_begin_date:
        raise ValidationFailedError("openings must use the books begin date")
    if not body.lines:
        if body.bills:
            raise ValidationFailedError("zero opening cannot contain outstanding bills")
        return OpeningPreview(
            posting_date=body.posting_date,
            base_currency=access.context.base_currency,
            total_debit=Decimal(0),
            total_credit=Decimal(0),
            bill_count=0,
            party_line_count=0,
            zero_opening=True,
        )
    from accounting.models.master_opening import MasterOpeningBalance

    reserved = select(MasterOpeningBalance.id).where(
        MasterOpeningBalance.company_id == access.context.company_id,
        MasterOpeningBalance.account_id.in_({line.account_id for line in body.lines}),
        MasterOpeningBalance.status.in_(["POSTING", "POSTED"]),
    )
    if master_opening_id is not None:
        reserved = reserved.where(MasterOpeningBalance.id != master_opening_id)
    if await db.scalar(reserved.limit(1)):
        raise ValidationFailedError(
            "This account opening was already posted or is posting during creation."
        )
    draft = JournalCreate(
        document_date=body.posting_date,
        posting_date=body.posting_date,
        description=body.description,
        lines=body.lines,
    )
    valued, accounts = await validate_lines(db, access, draft, kind="OPENING")
    party_lines = {
        i: line for i, line in enumerate(body.lines, 1) if accounts[line.account_id].kind == "PARTY"
    }
    totals: dict[int, Decimal] = {}
    identities: set[tuple[uuid.UUID, str, str]] = set()
    base_totals: dict[int, Decimal] = {}
    explicit_base: set[int] = set()
    sources: set[str] = set()
    for bill in body.bills:
        line = party_lines.get(bill.line_sequence)
        if line is None:
            raise ValidationFailedError("opening bill must reference a party journal line")
        if bill.document_date is not None and (
            bill.document_date > body.posting_date
            or (bill.due_date is not None and bill.due_date < bill.document_date)
        ):
            raise ValidationFailedError("invalid opening bill document or due date")
        account = accounts[line.account_id]
        debt = (account.party_role == "CUSTOMER") == (line.side == "DEBIT")
        if (
            (bill.document_kind == "INVOICE" and (account.party_role != "CUSTOMER" or not debt))
            or (bill.document_kind == "BILL" and (account.party_role != "SUPPLIER" or not debt))
            or (bill.document_kind in {"CREDIT_NOTE", "ADVANCE"} and debt)
        ):
            raise ValidationFailedError(
                "opening document kind differs from its party role or direction"
            )
        if bill.source_key:
            if bill.source_key.casefold() in sources:
                raise ValidationFailedError("opening document source keys must be unique")
            sources.add(bill.source_key.casefold())
        if bill.base_amount is not None:
            explicit_base.add(bill.line_sequence)
            base_totals[bill.line_sequence] = (
                base_totals.get(bill.line_sequence, Decimal(0)) + bill.base_amount
            )
        identity = (line.account_id, line.currency, bill.reference.casefold())
        if identity in identities:
            raise ValidationFailedError(
                "duplicate opening bill reference for this account and currency"
            )
        identities.add(identity)
        totals[bill.line_sequence] = totals.get(bill.line_sequence, Decimal(0)) + bill.amount
    for sequence in explicit_base:
        parts = [bill for bill in body.bills if bill.line_sequence == sequence]
        if (
            any(bill.base_amount is None for bill in parts)
            or base_totals[sequence] != valued[sequence - 1].base_amount
        ):
            raise ValidationFailedError(
                "every bill carrying value must be explicit and reconcile to its party line"
            )
    if any(totals.get(i) != line.amount for i, line in party_lines.items()):
        raise ValidationFailedError("opening bills must reconcile exactly to every party line")
    total = sum((line.base_amount for line in valued if line.entry.side == "DEBIT"), Decimal(0))
    return OpeningPreview(
        posting_date=body.posting_date,
        base_currency=access.context.base_currency,
        total_debit=total,
        total_credit=total,
        bill_count=len(body.bills),
        party_line_count=len(party_lines),
        zero_opening=False,
    )


async def require_available(
    db: AsyncSession, access: Access, replacement: uuid.UUID | None
) -> None:
    from accounting.tasks.master_opening_posting import company_batches

    existing = await db.scalar(
        select(OpeningBatch.id).where(
            OpeningBatch.company_id == access.context.company_id,
            OpeningBatch.status.in_(["DRAFT", "FINALIZED"]),
            company_batches(),
        )
    )
    if existing is not None:
        raise ConflictError("an opening batch is already pending or finalized")
    previous = await db.scalar(
        select(OpeningBatch)
        .where(
            OpeningBatch.company_id == access.context.company_id,
            OpeningBatch.status == "REVERSED",
            company_batches(),
        )
        .order_by(OpeningBatch.id.desc())
        .limit(1)
    )
    if (previous is None and replacement is not None) or (
        previous is not None and previous.id != replacement
    ):
        raise ConflictError("replacement must identify the latest reversed opening")


async def create(
    factory: async_sessionmaker[AsyncSession], access: Access, body: OpeningCreate, key: str
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        await require_available(db, access, body.replacement_of_id)
        await preview(db, access, body)
        row = cast(
            OpeningBatch,
            await create_row(
                db,
                access,
                "opening_batch",
                status="DRAFT",
                posting_date=body.posting_date,
                description=body.description,
                payload=body.model_dump(mode="json"),
                replacement_of_id=body.replacement_of_id,
                journal_id=None,
                finalized_at=None,
            ),
        )
        if body.lines:
            journal = await create_in_transaction(
                db,
                access,
                JournalCreate(
                    document_date=body.posting_date,
                    posting_date=body.posting_date,
                    description=body.description,
                    lines=body.lines,
                ),
                kind="OPENING",
                source_system="accounting",
                source_type="opening",
                source_id=str(row.id),
            )
            await change_row(db, access, "opening_batch", row, "update", journal_id=journal.id)
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["opening_batch"],
        "create",
        body,
        key,
        mutate,
        permission="accounting.finance.manage",
        status=201,
    )


async def finalize_zero(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        row = await company_object(
            db, OpeningBatch, object_id, company_id=access.context.company_id
        )
        if row.payload.get("workspace_revision_id"):
            raise ConflictError(
                "use the financial opening workspace lifecycle for this declaration"
            )
        if (
            row.status != "DRAFT"
            or row.row_version != body.expected_version
            or row.journal_id is not None
        ):
            raise ConflictError("only a current zero opening can finalize without a journal")
        await preview(db, access, OpeningCreate.model_validate(row.payload))
        await posting_period(db, access, row.posting_date)
        await change_row(
            db, access, "opening_batch", row, "finalize", status="FINALIZED", finalized_at=utcnow()
        )
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["opening_batch"],
        "finalize_zero",
        body,
        key,
        mutate,
        permission="accounting.finance.manage",
        object_id=object_id,
    )


async def void(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        row = await company_object(
            db, OpeningBatch, object_id, company_id=access.context.company_id
        )
        if row.payload.get("workspace_revision_id"):
            raise ConflictError("void this declaration through its financial opening workspace")
        if row.status != "DRAFT" or row.row_version != body.expected_version:
            raise ConflictError("only a current draft opening can be voided")
        if row.journal_id:
            journal = await company_object(db, Journal, row.journal_id, company_id=row.company_id)
            if journal.status not in {"DRAFT", "VOID"}:
                raise ConflictError("void the prepared journal before voiding its opening batch")
            if journal.status == "DRAFT":
                await change_row(db, access, "journal", journal, "void", status="VOID")
        await change_row(db, access, "opening_batch", row, "void", status="VOID")
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["opening_batch"],
        "void",
        body,
        key,
        mutate,
        permission="accounting.finance.manage",
        object_id=object_id,
    )


async def reopen_zero(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: OpeningReopen,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        row = await company_object(
            db, OpeningBatch, object_id, company_id=access.context.company_id
        )
        if (
            row.status != "FINALIZED"
            or row.journal_id is not None
            or row.row_version != body.expected_version
        ):
            raise ConflictError("only a current finalized zero opening can be reopened")
        trading = await db.scalar(
            select(Journal.id)
            .where(Journal.company_id == row.company_id, Journal.status.in_(["PREPARED", "POSTED"]))
            .limit(1)
        )
        if trading:
            raise ConflictError("zero opening correction is blocked after posting has started")
        await require_opening_revision_window(db, access, row.posting_date)
        await change_row(
            db,
            access,
            "opening_batch",
            row,
            "reverse",
            status="REVERSED",
            reversal_reason=body.reason,
        )
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["opening_batch"],
        "reopen_zero",
        body,
        key,
        mutate,
        permission="accounting.finance.manage",
        object_id=object_id,
    )
