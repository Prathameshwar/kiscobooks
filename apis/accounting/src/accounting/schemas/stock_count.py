"""Native cutoff and explicit physical observations; browser balances are excluded."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from voucher_execution.contracts import Contract
from voucher_execution.quantity import QuantityCapture
from voucher_execution.stock_decimal import Exact


class CountScope(Contract):
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID | None = None
    lot_id: uuid.UUID | None = None
    stock_date: dt.date = Field(ge=dt.date(1000, 1, 1))
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3 or any(ord(character) < 32 for character in value):
            raise ValueError("a physical count requires a printable meaningful reason")
        return value

    @field_validator("item_id", "warehouse_id", "bin_id", "lot_id")
    @classmethod
    def real_reference(cls, value: uuid.UUID | None) -> uuid.UUID | None:
        if value is not None and not value.int:
            raise ValueError("use real owner references")
        return value


class CountObservationInput(Contract):
    expected_revision: int = Field(strict=True, ge=1)
    observed_quantity: Exact = Field(ge=0)
    quantity_entry: QuantityCapture | None = None
    reason: str = Field(min_length=3, max_length=500)
    reviewed_unit_cost: Exact | None = Field(default=None, ge=0)
    cost_review_reason: str | None = Field(default=None, min_length=3, max_length=500)

    @field_validator("reason", "cost_review_reason")
    @classmethod
    def meaningful_reason(cls, value: str | None) -> str | None:
        return CountScope.meaningful_reason(value) if value is not None else None

    @model_validator(mode="after")
    def reviewed_cost(self) -> Self:
        if (self.reviewed_unit_cost is None) != (self.cost_review_reason is None):
            raise ValueError("explicit cost review requires both exact cost and its reason")
        if self.observed_quantity == 0 and self.quantity_entry is not None:
            raise ValueError("counted zero has no positive entered-unit conversion")
        return self


class CountDetail(CountScope):
    base_unit_id: uuid.UUID
    id: uuid.UUID
    root_id: uuid.UUID
    revision: int
    cutoff_at: dt.datetime
    cutoff_generation: int
    quantity_increment: Exact
    quantity_decimal_places: int
    book_quantity: Exact
    observed_quantity: Exact | None
    quantity_entry: QuantityCapture | None
    difference: Exact | None
    later_quantity: Exact
    current_quantity: Exact
    status: Literal["UNCOUNTED", "OBSERVED", "APPLIED"]
    cost_review_required: bool
    reviewed_unit_cost: Exact | None
    cost_review_reason: str | None


def difference(book: Decimal, observed: Decimal | None) -> Decimal | None:
    return observed - book if observed is not None else None
