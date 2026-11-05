"""Exact, source-backed foreign exchange quote commands."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

from billing_platform.listing import ListQuery
from pydantic import BeforeValidator, Field

from accounting.schemas.masters import Input


def exact_rate(value: Any) -> Any:
    if isinstance(value, float | bool):
        raise ValueError("exchange rates require exact decimal strings")
    return value


Rate = Annotated[
    Decimal,
    BeforeValidator(exact_rate),
    Field(gt=0, max_digits=27, decimal_places=12, allow_inf_nan=False),
]
Purpose = Literal["ACCOUNTING", "GST_GOODS", "GST_SERVICES", "REVALUATION", "SETTLEMENT"]
Source = Literal["MANUAL", "CSV", "CUSTOMS"]


class RateCandidate(Input):
    from_currency: str = Field(pattern=r"^[A-Z]{3}$")
    to_currency: str = Field(pattern=r"^[A-Z]{3}$")
    purpose: Purpose
    effective_date: dt.date
    rate: Rate
    source_kind: Source
    source_reference: str = Field(min_length=3, max_length=500)


class RateContext(Input):
    company_id: uuid.UUID
    base_currency: str
    allowed_currencies: list[str]
    multi_currency: bool


class RateImport(Input):
    csv_text: str = Field(min_length=1, max_length=1_000_000)
    source_reference: str = Field(min_length=3, max_length=500)


class RateDecision(Input):
    expected_version: int = Field(strict=True, ge=1)
    reason: str = Field(min_length=3, max_length=500)


class RateView(Input):
    id: uuid.UUID
    company_id: uuid.UUID
    from_currency: str
    to_currency: str
    purpose: Purpose
    effective_date: dt.date
    rate: Decimal
    source_kind: Source
    source_reference: str
    source_sha256: str
    status: Literal["CANDIDATE", "APPROVED", "WITHDRAWN"]
    row_version: int
    created_by: uuid.UUID | None
    approved_by: uuid.UUID | None
    approved_at: dt.datetime | None
    approval_reason: str | None
    withdrawn_by: uuid.UUID | None
    withdrawn_at: dt.datetime | None
    withdrawal_reason: str | None


class RateConversion(Input):
    amount: Annotated[
        Decimal,
        BeforeValidator(exact_rate),
        Field(ge=0, max_digits=19, decimal_places=4, allow_inf_nan=False),
    ]
    from_currency: str = Field(pattern=r"^[A-Z]{3}$")
    purpose: Purpose
    effective_date: dt.date


class RateConversionView(Input):
    rate_id: uuid.UUID
    rate: Decimal
    rate_date: dt.date
    source_reference: str
    from_currency: str
    to_currency: str
    amount: Decimal
    converted_amount: Decimal


class RateListQuery(ListQuery):
    from_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    purpose: Purpose | None = None
    status: Literal["CANDIDATE", "APPROVED", "WITHDRAWN"] | None = None
    effective_date: dt.date | None = None


class RateListItem(Input):
    id: uuid.UUID
    from_currency: str
    to_currency: str
    purpose: Purpose
    effective_date: dt.date
    rate: Decimal
    source_kind: Source
    status: Literal["CANDIDATE", "APPROVED", "WITHDRAWN"]


class RateUsageView(Input):
    id: uuid.UUID
    journal_line_id: uuid.UUID
    quote_id: uuid.UUID
    purpose: Purpose
    effective_date: dt.date
    rate: Decimal
    source_sha256: str
