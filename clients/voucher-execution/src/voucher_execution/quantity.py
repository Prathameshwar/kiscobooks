"""Entered stock quantities and authenticated unit facts; base quantity stays explicit."""

import uuid
from typing import Literal, Self

from pydantic import Field, StrictBool, model_validator

from voucher_execution.contracts import Contract
from voucher_execution.stock_decimal import Exact


class QuantityCapture(Contract):
    entered_unit_id: uuid.UUID
    unit_revision_id: uuid.UUID
    entered_quantity: Exact = Field(gt=0)
    measured_base_quantity: Exact | None = Field(
        default=None, gt=0, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def real_references(self) -> Self:
        if not self.entered_unit_id.int or not self.unit_revision_id.int:
            raise ValueError("quantity evidence requires published unit references")
        return self


class QuantityUnitFact(Contract):
    item_id: uuid.UUID
    unit_id: uuid.UUID
    revision_id: uuid.UUID
    usage_role: Literal["BASE", "SALE", "PURCHASE", "BOTH", "PACK", "MEASURED"]
    conversion_mode: Literal["FIXED", "MEASURED"]
    numerator: str | None = Field(pattern=r"^[1-9][0-9]{0,18}$")
    denominator: str | None = Field(pattern=r"^[1-9][0-9]{0,18}$")
    quantity_increment: Exact = Field(gt=0)
    quantity_decimal_places: int = Field(strict=True, ge=0, le=4)
    fractional_entry: StrictBool

    @model_validator(mode="after")
    def exact_mode(self) -> Self:
        if self.conversion_mode == "FIXED":
            if self.numerator is None or self.denominator is None:
                raise ValueError("fixed quantity requires an exact ratio")
            if max(int(self.numerator), int(self.denominator)) >= 2**63:
                raise ValueError("quantity ratio exceeds signed BIGINT")
        elif self.numerator is not None or self.denominator is not None:
            raise ValueError("measured actual quantity cannot use a nominal ratio")
        return self
