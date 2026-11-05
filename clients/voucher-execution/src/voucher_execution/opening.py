"""Typed opening evidence; never a custom-field balance or client-supplied authority."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, StrictBool, field_validator, model_validator

from voucher_execution.contracts import Contract
from voucher_execution.stock_decimal import Exact


class OpeningCapture(Contract):
    source_key: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    entered_unit_id: uuid.UUID
    unit_revision_id: uuid.UUID
    entered_quantity: Exact = Field(gt=0)
    measured_base_quantity: Exact | None = Field(
        default=None, gt=0, exclude_if=lambda value: value is None
    )
    cost_mode: Literal["RATE", "VALUE"]
    unit_cost: Exact | None = Field(default=None, ge=0)
    priced_quantity: Exact = Field(default=Decimal("1"), gt=0)
    history_known: StrictBool
    received_on: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    cohort_order: int = Field(default=1, strict=True, ge=1, le=1_000_000)

    @field_validator("source_key")
    @classmethod
    def canonical_key(cls, value: str) -> str:
        return value.lower()

    @field_validator("entered_unit_id", "unit_revision_id")
    @classmethod
    def real_id(cls, value: uuid.UUID) -> uuid.UUID:
        if not value.int:
            raise ValueError("opening units require real published references")
        return value

    @model_validator(mode="after")
    def evidence(self) -> Self:
        if (self.cost_mode == "RATE") != (self.unit_cost is not None):
            raise ValueError("RATE supplies unit cost; VALUE uses the explicit received value")
        if self.history_known != (self.received_on is not None):
            raise ValueError("known opening history requires its original receipt date")
        return self


class OpeningUnitFact(Contract):
    item_id: uuid.UUID
    unit_id: uuid.UUID
    revision_id: uuid.UUID
    conversion_mode: Literal["FIXED", "MEASURED"] = Field(
        default="FIXED", exclude_if=lambda value: value == "FIXED"
    )
    numerator: int | None = Field(strict=True, gt=0)
    denominator: int | None = Field(strict=True, gt=0)
    quantity_increment: Exact = Field(gt=0)
    quantity_decimal_places: int = Field(strict=True, ge=0, le=4)

    @model_validator(mode="after")
    def actual_measurement_contract(self) -> Self:
        if self.conversion_mode == "FIXED" and (self.numerator is None or self.denominator is None):
            raise ValueError("fixed opening requires an exact ratio")
        if self.conversion_mode == "MEASURED" and (
            self.numerator is not None or self.denominator is not None
        ):
            raise ValueError("measured opening cannot use a nominal ratio")
        return self
