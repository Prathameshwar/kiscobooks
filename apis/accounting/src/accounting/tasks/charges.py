"""Separate charge approval, immutable posting and coverage-preserving waiver."""

import datetime as dt
import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.idempotency import CommandResult
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.charges import ChargeAssessment, ChargePolicy
from accounting.models.ledger import Journal
from accounting.models.subledger import OpenItem
from accounting.schemas.charges import ChargeApprove, ChargeRequest
from accounting.schemas.ledger import JournalCreate
from accounting.tasks.charge_calculation import preview
from accounting.tasks.finance_records import change_row, create_row
from accounting.tasks.financial_commands import (
    FinancialEffect,
    financial_command,
)
from accounting.tasks.fiscal import posting_period
from accounting.tasks.journal_drafts import create_in_transaction, lines
from accounting.tasks.party_documents import enforce_holds, party_account, policy_at


async def create(
    factory: async_sessionmaker[AsyncSession], access: Access, body: ChargeRequest, key: str
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        value = await preview(db, access, body)
        if value.amount <= 0:
            raise ConflictError("no additional charge is due for this interval")
        return FinancialEffect(
            await create_row(
                db,
                access,
                "charge_assessment",
                **value.model_dump(),
                posting_date=body.posting_date,
                due_date=body.due_date,
                exchange_rate=body.exchange_rate,
                external_reference=body.external_reference,
                status="DRAFT",
                journal_id=None,
                approved_by=None,
                approved_at=None,
                reason=None,
            )
        )

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["charge_assessment"],
        "create",
        body,
        key,
        mutate,
        permission="accounting.charges.manage",
        status=201,
    )


async def revalidate(
    db: AsyncSession, access: Access, row: ChargeAssessment
) -> tuple[OpenItem, ChargePolicy]:
    value = await preview(
        db, access, ChargeRequest.model_validate(row.snapshot["request"]), exclude=row.id
    )
    if (
        value.input_hash != row.input_hash
        or value.amount != row.amount
        or value.cumulative_amount != row.cumulative_amount
    ):
        raise ConflictError("charge assessment is stale; reject it and calculate again")
    item = await company_object(db, OpenItem, row.item_id, company_id=row.company_id)
    policy = await company_object(db, ChargePolicy, row.policy_id, company_id=row.company_id)
    return item, policy


async def approve(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: ChargeApprove,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        row = await company_object(
            db, ChargeAssessment, object_id, company_id=access.context.company_id
        )
        if row.status != "DRAFT" or row.row_version != body.expected_version:
            raise ConflictError("charge assessment version or status changed")
        if row.created_by == access.actor.user_id:
            raise PermissionDeniedError("charges require a different approver")
        item, policy = await revalidate(db, access, row)
        if item.role == "SUPPLIER" and not row.external_reference:
            raise ConflictError("supplier charge requires its external debit reference")
        account = await party_account(db, access, item.account_id)
        enforce_holds(await policy_at(db, access, account, row.posting_date), "CHARGE")
        from accounting.tasks.charge_tax import journal_lines

        journal = await create_in_transaction(
            db,
            access,
            JournalCreate(
                document_date=row.posting_date,
                posting_date=row.posting_date,
                description="Overdue charge assessment",
                lines=await journal_lines(db, access, row, item, policy),
            ),
            kind="CHARGE",
            source_system="accounting",
            source_type="charge",
            source_id=str(row.id),
        )
        await change_row(
            db,
            access,
            "charge_assessment",
            row,
            "approve",
            status="APPROVED",
            approved_by=access.actor.user_id,
            approved_at=utcnow(),
            reason=body.reason,
            journal_id=journal.id,
        )
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["charge_assessment"],
        "approve",
        body,
        key,
        mutate,
        permission="accounting.charges.approve",
        object_id=object_id,
    )


async def dispose(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: ChargeApprove,
    key: str,
    *,
    waive: bool,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        row = await company_object(
            db, ChargeAssessment, object_id, company_id=access.context.company_id
        )
        if row.status not in {"DRAFT", "APPROVED"} or row.row_version != body.expected_version:
            raise ConflictError("only an unposted current assessment can be waived or rejected")
        if waive:
            if row.created_by == access.actor.user_id:
                raise PermissionDeniedError("charge waiver requires a different approver")
            await revalidate(db, access, row)
            await posting_period(db, access, row.posting_date)
        if row.journal_id:
            journal = await company_object(db, Journal, row.journal_id, company_id=row.company_id)
            if journal.status not in {"DRAFT", "VOID"}:
                raise ConflictError(
                    "void the prepared charge journal before disposing its assessment"
                )
            if journal.status == "DRAFT":
                await change_row(db, access, "journal", journal, "void", status="VOID")
        await change_row(
            db,
            access,
            "charge_assessment",
            row,
            "waive" if waive else "reject",
            status="WAIVED" if waive else "REJECTED",
            reason=body.reason,
            approved_by=access.actor.user_id if waive else row.approved_by,
            approved_at=utcnow() if waive else row.approved_at,
        )
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["charge_assessment"],
        "waive" if waive else "reject",
        body,
        key,
        mutate,
        permission="accounting.charges.approve" if waive else "accounting.charges.manage",
        object_id=object_id,
    )


async def before_post(db: AsyncSession, access: Access, journal: Journal) -> None:
    access.actor.require_scope(
        "accounting.charges.manage", target=ScopePath(company_id=journal.company_id)
    )
    row = await db.scalar(
        select(ChargeAssessment).where(
            ChargeAssessment.company_id == journal.company_id,
            ChargeAssessment.journal_id == journal.id,
        )
    )
    if (
        row is None
        or row.status != "APPROVED"
        or row.approved_by is None
        or row.approved_by == row.created_by
    ):
        raise ConflictError("charge journal has no separately approved assessment")
    item, policy = await revalidate(db, access, row)
    from accounting.tasks.charge_tax import journal_lines
    from accounting.tasks.journal_drafts import line_input

    expected = await journal_lines(db, access, row, item, policy)
    stored = await lines(db, journal.company_id, journal.id)
    if [line_input(line) for line in stored] != expected:
        raise ConflictError("charge journal differs from its approved calculation or tax evidence")
    account = await party_account(db, access, item.account_id)
    enforce_holds(await policy_at(db, access, account, journal.posting_date), "CHARGE")


async def after_post(db: AsyncSession, access: Access, journal: Journal) -> None:
    row = await db.scalar(
        select(ChargeAssessment).where(
            ChargeAssessment.company_id == journal.company_id,
            ChargeAssessment.journal_id == journal.id,
        )
    )
    if row is None:
        raise ConflictError("charge assessment is missing")
    stored = await lines(db, journal.company_id, journal.id)
    from accounting.tasks.subledger_posting import make_items

    await make_items(
        db,
        access,
        journal,
        stored[0],
        [
            {
                "amount": str(stored[0].amount),
                "reference": row.external_reference or journal.number,
                "document_date": journal.document_date.isoformat(),
                "due_date": row.due_date.isoformat(),
            }
        ],
        {
            "charge_assessment_id": str(row.id),
            "charge_policy_id": str(row.policy_id),
            "original_item_id": str(row.item_id),
        },
    )
    await change_row(db, access, "charge_assessment", row, "post", status="POSTED")


async def guard_history(
    db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID, date: dt.date
) -> None:
    existing = await db.scalar(
        select(ChargeAssessment.id)
        .where(
            ChargeAssessment.company_id == company_id,
            ChargeAssessment.item_id == item_id,
            ChargeAssessment.status.in_(["POSTED", "WAIVED"]),
            ChargeAssessment.coverage_end_date > date,
        )
        .limit(1)
    )
    if existing:
        raise ConflictError("reverse later charge coverage before changing its principal history")


async def reversal_guard(db: AsyncSession, access: Access, original: Journal) -> None:
    row = await db.scalar(
        select(ChargeAssessment).where(
            ChargeAssessment.company_id == original.company_id,
            ChargeAssessment.journal_id == original.id,
        )
    )
    if row is None:
        return
    later = await db.scalar(
        select(ChargeAssessment.id)
        .where(
            ChargeAssessment.company_id == row.company_id,
            ChargeAssessment.item_id == row.item_id,
            ChargeAssessment.status.not_in(["REVERSED", "REJECTED"]),
            ChargeAssessment.coverage_end_date > row.coverage_end_date,
        )
        .limit(1)
    )
    if later:
        raise ConflictError("reverse later charge assessments first")


async def after_reversal(db: AsyncSession, access: Access, original: Journal) -> None:
    row = await db.scalar(
        select(ChargeAssessment).where(
            ChargeAssessment.company_id == original.company_id,
            ChargeAssessment.journal_id == original.id,
        )
    )
    if row:
        await change_row(db, access, "charge_assessment", row, "reverse", status="REVERSED")
