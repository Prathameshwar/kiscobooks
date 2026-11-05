"""Company-year readiness uses retained books, never synthetic annual opening vouchers."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.models.fiscal import FinancialSetup, FiscalPeriod, FiscalYear
from accounting.models.ledger import Journal
from accounting.models.subledger import OpeningBatch
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.tasks.finance_records import require_fields
from accounting.tasks.fiscal import frozen_settings_match
from accounting.tasks.reconciliation import closing_checks


async def readiness(db: AsyncSession, current: Access, year_id: uuid.UUID) -> dict[str, Any]:
    for name, fields in (
        ("fiscal_year", {"start_date", "end_date"}),
        (
            "fiscal_period",
            {"fiscal_year_id", "code", "start_date", "end_date", "status", "row_version"},
        ),
        ("journal", {"status", "posting_date"}),
        ("opening_batch", {"status"}),
        (
            "financial_setup",
            {
                "books_begin_date",
                "fiscal_year_start_month",
                "fiscal_year_start_day",
                "amount_precision",
                "rounding_mode",
                "base_currency",
            },
        ),
    ):
        require_fields(current, name, fields)
    year = await company_object(db, FiscalYear, year_id, company_id=current.context.company_id)
    periods = list(
        await db.scalars(
            select(FiscalPeriod)
            .where(
                FiscalPeriod.company_id == year.company_id, FiscalPeriod.fiscal_year_id == year.id
            )
            .order_by(FiscalPeriod.start_date)
            .limit(13)
        )
    )
    cursor = year.start_date
    continuous = bool(periods)
    for period in periods:
        if period.start_date != cursor or period.end_date < period.start_date:
            continuous = False
        cursor = period.end_date + dt.timedelta(days=1)
    continuous = continuous and cursor == year.end_date + dt.timedelta(days=1)
    pending_journals = (
        await db.scalar(
            select(func.count(Journal.id)).where(
                Journal.company_id == year.company_id,
                Journal.posting_date.between(year.start_date, year.end_date),
                Journal.status.in_(["DRAFT", "PREPARED"]),
            )
        )
        or 0
    )
    pending_executions = (
        await db.scalar(
            select(func.count(VoucherMoneyIntent.id)).where(
                VoucherMoneyIntent.company_id == year.company_id,
                VoucherMoneyIntent.posting_date.between(year.start_date, year.end_date),
                VoucherMoneyIntent.status == "PREPARED",
            )
        )
        or 0
    )
    opening = await db.scalar(
        select(OpeningBatch.id)
        .where(OpeningBatch.company_id == year.company_id, OpeningBatch.status == "FINALIZED")
        .limit(1)
    )
    setup = await db.scalar(
        select(FinancialSetup).where(FinancialSetup.company_id == year.company_id)
    )
    blockers = []
    if not continuous:
        blockers.append("INCOMPLETE_CALENDAR")
    if opening is None:
        blockers.append("OPENING_NOT_FINALIZED")
    if (
        setup is None
        or current.context.finance is None
        or not frozen_settings_match(setup, current)
    ):
        blockers.append("CONFIGURATION_CHANGED")
    if current.context.finance is not None and not current.context.finance.company_active:
        blockers.append("COMPANY_INACTIVE")
    close_blockers = list(blockers)
    if pending_journals or pending_executions:
        close_blockers.append("PENDING_FINANCIAL_ENTRIES")
    if any(period.status == "FUTURE" for period in periods):
        close_blockers.append("UNOPENED_PERIODS")
    for period in periods:
        try:
            await closing_checks(db, current, period)
        except ConflictError:
            close_blockers.append("OWNER_CLOSE_CHECKS_PENDING")
            break
    return {
        "fiscal_year_id": str(year.id),
        "start_date": year.start_date.isoformat(),
        "end_date": year.end_date.isoformat(),
        "ready_for_posting": not blockers and any(period.status == "OPEN" for period in periods),
        "blockers": blockers,
        "pending_journals": pending_journals,
        "pending_executions": pending_executions,
        "close_ready": not close_blockers,
        "close_blockers": close_blockers,
        "balance_basis": "CUMULATIVE_RETAINED_POSTED_LEDGER",
        "annual_opening_voucher_required": False,
        "periods": [
            {
                "id": str(period.id),
                "code": period.code,
                "status": period.status,
                "row_version": period.row_version,
            }
            for period in periods
        ],
    }
