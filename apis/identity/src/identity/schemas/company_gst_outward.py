import datetime as dt
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from identity.schemas.base import StrictModel


class GstOutwardProfileCreate(StrictModel):
    registration_id: uuid.UUID
    annual_turnover: str
    currency: Literal["INR"] = "INR"
    rule_14a: bool
    valid_from: dt.date
    valid_to: dt.date | None = None
    reference: str = Field(min_length=1, max_length=120)
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("annual_turnover", mode="before")
    @classmethod
    def exact_turnover(cls, value: object) -> str:
        if not isinstance(value, str | Decimal):
            raise ValueError("turnover requires an exact decimal string")
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("turnover requires a valid exact decimal string") from exc
        if (
            not result.is_finite()
            or result < 0
            or result >= Decimal("1000000000000000")
            or result != result.quantize(Decimal("0.0001"))
        ):
            raise ValueError("turnover exceeds non-negative DECIMAL(19,4)")
        return format(result, ".4f")

    @model_validator(mode="after")
    def dated(self) -> Self:
        if self.valid_from.day != 1 or (
            self.valid_to and (self.valid_to.day != 1 or self.valid_to <= self.valid_from)
        ):
            raise ValueError(
                "reporting profile must cover complete statutory months; end is exclusive"
            )
        return self


class GstOutwardProfileItem(GstOutwardProfileCreate):
    id: uuid.UUID


class GstOutwardProfileClose(StrictModel):
    valid_to: dt.date


class GstOutwardProfileSetup(StrictModel):
    can_manage: bool
    create_schema: dict[str, Any]
