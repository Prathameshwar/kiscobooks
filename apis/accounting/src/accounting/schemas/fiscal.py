"""Financial setup and fiscal control request/response contracts."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import Field

from accounting.schemas.masters import Detail, ExpectedVersion, Input
from accounting.schemas.query import MasterQuery

PeriodStatus = Literal["FUTURE", "OPEN", "SOFT_CLOSED", "CLOSED", "LOCKED"]


class FinancialSetupDetail(Detail):
    base_currency: str | None = None
    books_begin_date: dt.date | None = None
    fiscal_year_start_month: int | None = None
    fiscal_year_start_day: int | None = None
    amount_precision: int | None = None
    rounding_mode: str | None = None
    timezone: str | None = None
    configuration_hash: str | None = None
    first_posted_at: dt.datetime | None = None


class FinancialSetupReconcile(ExpectedVersion):
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=3, max_length=500)


class FinancialSettingChange(Input):
    field: str
    before: str
    after: str


class FinancialSetupReview(Input):
    expected_version: int
    configuration_hash: str
    changes: list[FinancialSettingChange]


class FiscalYearGenerate(Input):
    start_year: int = Field(strict=True, ge=1900, le=9997)


class FiscalYearDetail(Detail):
    code: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None


class FiscalYearListItem(Detail):
    code: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None


class FiscalPeriodDetail(Detail):
    fiscal_year_id: uuid.UUID | None = None
    sequence: int | None = None
    code: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    status: PeriodStatus | None = None


class FiscalPeriodListItem(Detail):
    fiscal_year_id: uuid.UUID | None = None
    sequence: int | None = None
    code: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    status: PeriodStatus | None = None


class PeriodTransition(ExpectedVersion):
    status: PeriodStatus
    reason: str = Field(min_length=3, max_length=500)


class FiscalQuery(MasterQuery):
    status: PeriodStatus | None = None
    fiscal_year_id: uuid.UUID | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None


class FiscalTransitionDetail(Detail):
    period_id: uuid.UUID | None = None
    from_status: PeriodStatus | None = None
    to_status: PeriodStatus | None = None
    reason: str | None = None


class FiscalTransitionListItem(Detail):
    period_id: uuid.UUID | None = None
    from_status: PeriodStatus | None = None
    to_status: PeriodStatus | None = None


class ReadinessPeriod(Input):
    id: uuid.UUID
    code: str
    status: PeriodStatus
    row_version: int


class FiscalReadiness(Input):
    fiscal_year_id: uuid.UUID
    start_date: dt.date
    end_date: dt.date
    ready_for_posting: bool
    blockers: list[str]
    pending_journals: int
    pending_executions: int
    close_ready: bool
    close_blockers: list[str]
    balance_basis: Literal["CUMULATIVE_RETAINED_POSTED_LEDGER"]
    annual_opening_voucher_required: Literal[False]
    periods: list[ReadinessPeriod]


class NextYearQuery(Input):
    source_year_id: uuid.UUID | None = None


class NextYearSource(Input):
    id: uuid.UUID
    code: str
    start_date: dt.date
    end_date: dt.date


class NextYearPeriod(Input):
    id: uuid.UUID | None = None
    sequence: int
    code: str
    start_date: dt.date
    end_date: dt.date
    status: PeriodStatus
    row_version: int | None = None


class NextYearPreview(Input):
    company_id: uuid.UUID
    source_year: NextYearSource | None
    start_year: int
    code: str
    start_date: dt.date
    end_date: dt.date
    existing_year_id: uuid.UUID | None
    can_generate: bool
    blockers: list[str]
    periods: list[NextYearPeriod]
