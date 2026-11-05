"""Explicit first-time zero declaration, independent of balance-restatement authority."""

from typing import Literal

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.idempotency import CommandResult
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.fiscal import FinancialSetup, FiscalPeriod
from accounting.models.ledger import Journal
from accounting.models.stock import StockPosting
from accounting.models.subledger import OpeningBatch
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.schemas.subledger import OpeningCreate, ZeroOpeningConfirm, ZeroOpeningReview
from accounting.tasks.finance_records import change_row, create_row, require_fields
from accounting.tasks.financial_commands import FinancialEffect, financial_command, require_any
from accounting.tasks.fiscal import setup

PERMISSIONS = ("opening_balance.initialize_zero", "accounting.finance.manage")
Blocker = Literal[
    "EXISTING_OPENING_OR_ACTIVITY", "BOOKS_PERIOD_NOT_OPEN", "OPENING_ALREADY_FINALIZED"
]


async def blocker(db: AsyncSession, current: Access, books: FinancialSetup) -> Blocker | None:
    company = current.context.company_id
    if books.first_posted_at is not None:
        return "EXISTING_OPENING_OR_ACTIVITY"
    # Any historical opening, including a voided/reversed one, needs the controller.
    require_fields(current, "opening_batch", {"status"})
    opening = await db.scalar(
        select(OpeningBatch)
        .where(OpeningBatch.company_id == company)
        .order_by(OpeningBatch.id.desc())
        .limit(1)
    )
    if opening is not None:
        return (
            "OPENING_ALREADY_FINALIZED"
            if opening.status == "FINALIZED"
            else "EXISTING_OPENING_OR_ACTIVITY"
        )
    for model in (Journal, StockPosting):
        if await db.scalar(select(model.id).where(model.company_id == company).limit(1)):
            return "EXISTING_OPENING_OR_ACTIVITY"
    pending = await db.scalar(
        select(VoucherMoneyIntent.id)
        .where(
            VoucherMoneyIntent.company_id == company,
            VoucherMoneyIntent.status.in_(("PREPARED", "COMMITTED")),
        )
        .limit(1)
    )
    if pending:
        return "EXISTING_OPENING_OR_ACTIVITY"
    periods = list(
        await db.scalars(
            select(FiscalPeriod)
            .where(
                FiscalPeriod.company_id == company,
                FiscalPeriod.start_date <= books.books_begin_date,
                FiscalPeriod.end_date >= books.books_begin_date,
            )
            .limit(2)
        )
    )
    if len(periods) != 1 or periods[0].status != "OPEN":
        return "BOOKS_PERIOD_NOT_OPEN"
    return None


async def review(db: AsyncSession, current: Access) -> ZeroOpeningReview:
    require_any(current, PERMISSIONS)
    books = await setup(db, current)
    require_fields(current, "financial_setup", {"books_begin_date"}, row=books)
    problem = await blocker(db, current, books)
    return ZeroOpeningReview(
        company_id=current.context.company_id,
        expected_setup_version=books.row_version,
        books_begin_date=books.books_begin_date,
        eligible=problem is None,
        blocker=problem,
    )


async def confirm(
    factory: async_sessionmaker[AsyncSession], current: Access, body: ZeroOpeningConfirm, key: str
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        books = await setup(db, current)
        require_fields(current, "financial_setup", {"books_begin_date"}, row=books)
        if books.row_version != body.expected_setup_version:
            raise ConflictError("book settings changed; review the zero opening again")
        problem = await blocker(db, current, books)
        if problem:
            raise ConflictError(
                "open the books begin-date period before confirming a zero opening"
                if problem == "BOOKS_PERIOD_NOT_OPEN"
                else "existing opening balances or activity require a financial controller"
            )
        # Request fields cannot supply amounts, accounts, bills, dates or replacements.
        opening = OpeningCreate(posting_date=books.books_begin_date, description=body.reason)
        row = await create_row(
            db,
            current,
            "opening_batch",
            status="DRAFT",
            posting_date=opening.posting_date,
            description=opening.description,
            payload=opening.model_dump(mode="json"),
            replacement_of_id=None,
            journal_id=None,
            finalized_at=None,
        )
        await change_row(
            db, current, "opening_batch", row, "finalize", status="FINALIZED", finalized_at=utcnow()
        )
        return FinancialEffect(row)

    return await financial_command(
        factory,
        current,
        FINANCIAL_BY_NAME["opening_batch"],
        "confirm_initial_zero",
        body,
        key,
        mutate,
        permission=PERMISSIONS,
        status=201,
    )
