"""Read-only next-year calendar proposal; writes retain the existing command boundary."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import NotFoundError, PermissionDeniedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.domain.fiscal import monthly_periods
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.fiscal import FinancialSetup, FiscalPeriod, FiscalYear
from accounting.tasks.access import authorize, writable
from accounting.tasks.finance_records import require_fields
from accounting.tasks.fiscal import frozen_settings_match

YEAR_FIELDS = {"code", "start_date", "end_date"}
SETUP_FIELDS = {
    "books_begin_date",
    "fiscal_year_start_month",
    "fiscal_year_start_day",
    "amount_precision",
    "rounding_mode",
    "base_currency",
}
PERIOD_FIELDS = {
    "fiscal_year_id",
    "sequence",
    "code",
    "start_date",
    "end_date",
    "status",
    "row_version",
}


async def preview(
    db: AsyncSession, current: Access, source_year_id: uuid.UUID | None
) -> dict[str, Any]:
    require_fields(current, "fiscal_year", YEAR_FIELDS)
    require_fields(current, "financial_setup", SETUP_FIELDS)
    require_fields(current, "fiscal_period", PERIOD_FIELDS)
    company = current.context.company_id
    # Resolve explicit objects before looking up another company's setup: scope is enforced
    # even when that company has no books. Global tenant filtering is still in effect.
    source = (
        await company_object(db, FiscalYear, source_year_id, company_id=company)
        if source_year_id
        else await db.scalar(
            select(FiscalYear)
            .where(FiscalYear.company_id == company)
            .order_by(FiscalYear.start_date.desc(), FiscalYear.id.desc())
            .limit(1)
        )
    )
    config = await db.scalar(select(FinancialSetup).where(FinancialSetup.company_id == company))
    if config is None:
        raise NotFoundError("initialize company accounting books before starting a financial year")
    require_fields(current, "financial_setup", SETUP_FIELDS, row=config)
    if source:
        require_fields(current, "fiscal_year", YEAR_FIELDS, row=source)
    start_year = source.start_date.year + 1 if source else config.books_begin_date.year
    if (
        not source
        and config.books_begin_date
        < monthly_periods(start_year, config.fiscal_year_start_month, config.fiscal_year_start_day)[
            0
        ].start_date
    ):
        start_year -= 1
    spans = monthly_periods(
        start_year, config.fiscal_year_start_month, config.fiscal_year_start_day
    )
    first, last = spans[0].start_date, spans[-1].end_date
    target = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.company_id == company,
            FiscalYear.start_date == first,
        )
    )
    blockers = []
    if source:
        source_spans = monthly_periods(
            source.start_date.year, config.fiscal_year_start_month, config.fiscal_year_start_day
        )
        if (
            source.start_date != source_spans[0].start_date
            or source.end_date != source_spans[-1].end_date
            or source.end_date + dt.timedelta(days=1) != first
        ):
            blockers.append("SOURCE_CALENDAR_MISMATCH")
    if not frozen_settings_match(config, current):
        blockers.append("CONFIGURATION_CHANGED")
    if current.context.finance and not current.context.finance.company_active:
        blockers.append("COMPANY_INACTIVE")
    periods = []
    if target:
        require_fields(current, "fiscal_year", YEAR_FIELDS, row=target)
        if target.end_date != last:
            blockers.append("TARGET_CALENDAR_MISMATCH")
        stored = list(
            await db.scalars(
                select(FiscalPeriod)
                .where(
                    FiscalPeriod.company_id == company,
                    FiscalPeriod.fiscal_year_id == target.id,
                )
                .order_by(FiscalPeriod.sequence)
                .limit(13)
            )
        )
        if len(stored) != 12 or any(
            (row.sequence, row.start_date, row.end_date)
            != (span.sequence, span.start_date, span.end_date)
            for row, span in zip(stored, spans, strict=False)
        ):
            blockers.append("INCOMPLETE_CALENDAR")
        for row in stored:
            require_fields(current, "fiscal_period", PERIOD_FIELDS, row=row)
            periods.append(
                {
                    "id": row.id,
                    "sequence": row.sequence,
                    "code": row.code,
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                    "status": row.status,
                    "row_version": row.row_version,
                }
            )
    else:
        overlap = await db.scalar(
            select(FiscalYear.id)
            .where(
                FiscalYear.company_id == company,
                FiscalYear.start_date <= last,
                FiscalYear.end_date >= first,
            )
            .limit(1)
        )
        if overlap:
            blockers.append("OVERLAPPING_CALENDAR")
        periods = [
            {
                "sequence": span.sequence,
                "code": f"P{span.sequence:02d}",
                "start_date": span.start_date,
                "end_date": span.end_date,
                "status": "FUTURE",
            }
            for span in spans
        ]
    can_generate = not blockers and not current.actor.impersonation_id
    try:
        spec = FINANCIAL_BY_NAME["fiscal_year"]
        authorize(current, spec, "manage")
        writable(current, spec, {}, {"start_year": start_year})
    except PermissionDeniedError:
        can_generate = False
    return {
        "company_id": company,
        "source_year": {
            "id": source.id,
            "code": source.code,
            "start_date": source.start_date,
            "end_date": source.end_date,
        }
        if source
        else None,
        "start_year": start_year,
        "code": f"FY{start_year}-{last.year}",
        "start_date": first,
        "end_date": last,
        "existing_year_id": target.id if target else None,
        "can_generate": can_generate,
        "blockers": blockers,
        "periods": periods,
    }
