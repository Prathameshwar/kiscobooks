"""Read-only TDS/TCS withholding preview contract."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from accounting.schemas.ledger import BusinessDate, exact_input
from accounting.schemas.masters import DecimalInput, Input

NonnegativeAmount = Annotated[
    DecimalInput,
    BeforeValidator(exact_input),
    Field(ge=0, max_digits=19, decimal_places=4, allow_inf_nan=False),
]


class WithholdingPreviewRequest(Input):
    party_id: uuid.UUID
    section_id: uuid.UUID
    posting_date: BusinessDate
    amount: NonnegativeAmount
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    ytd_amount: NonnegativeAmount = Decimal(0)
    ytd_withheld_base: NonnegativeAmount = Decimal(0)
    certificate_consumed: NonnegativeAmount = Decimal(0)


class WithholdingPreviewPortion(Input):
    base_amount: DecimalInput
    rate_percent: DecimalInput
    rate_source: Literal["CERTIFICATE", "NO_PAN", "NORMAL"]
    amount: DecimalInput


class WithholdingPreview(Input):
    kind: Literal["TDS", "TCS"]
    party_id: uuid.UUID
    section_id: uuid.UUID
    posting_date: dt.date
    applies: bool
    reason: Literal["WITHHELD", "NOT_DEDUCTIBLE", "BELOW_THRESHOLD"]
    profile_id: uuid.UUID
    rate_id: uuid.UUID | None
    certificate_id: uuid.UUID | None
    threshold_crossed: bool
    currency: str
    base_amount: DecimalInput
    withholding_amount: DecimalInput
    portions: list[WithholdingPreviewPortion]
