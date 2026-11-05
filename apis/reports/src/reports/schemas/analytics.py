"""Typed business analytics periods and explicit diagnostic thresholds."""

import uuid
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from reports.schemas.report_parameters import Comparison, DateRange


class AnalyticsParameters(DateRange, Comparison):
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    search: str = Field(default="", max_length=200)
    grain: Literal["DAY", "MONTH"] = "MONTH"

    @field_validator("search")
    @classmethod
    def searchable(cls, value: str) -> str:
        value = " ".join(value.split())
        if value and len(value) < 2:
            raise ValueError("search requires at least two characters")
        return value

    @model_validator(mode="after")
    def bounded_periods(self) -> Self:
        for begin, end in (
            (self.date_from, self.date_to),
            (self.comparative_from, self.comparative_to),
        ):
            if begin and end and (end - begin).days > 3660:
                raise ValueError("analytics periods support at most ten years")
        return self


class ProfitParameters(DateRange, Comparison):
    # Company P&L uses base currency; product rows retain their own currency groups.
    search: str = Field(default="", max_length=200)
    grain: Literal["MONTH"] = "MONTH"

    @field_validator("search")
    @classmethod
    def searchable(cls, value: str) -> str:
        return AnalyticsParameters.searchable(value)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        AnalyticsParameters.model_validate(
            self.model_dump(mode="json", include=set(AnalyticsParameters.model_fields))
        )
        return self


class CustomerParameters(AnalyticsParameters):
    inactive_days: int = Field(default=90, ge=1, le=730)
    segment: Literal["ALL", "ACTIVE", "REPEAT", "FIRST_OBSERVED", "INACTIVE", "DECLINING"] = "ALL"


class BuyerProfitParameters(DateRange, Comparison):
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    party_id: uuid.UUID | None = None
    search: str = Field(default="", max_length=200)

    @field_validator("search")
    @classmethod
    def searchable(cls, value: str) -> str:
        return AnalyticsParameters.searchable(value)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        AnalyticsParameters.model_validate(
            self.model_dump(mode="json", include=set(AnalyticsParameters.model_fields))
        )
        return self


class ProductProfitParameters(BuyerProfitParameters):
    item_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None


class ExpenseParameters(ProfitParameters):
    increase_percent: int = Field(default=25, ge=1, le=1000)
    material_amount: str = Field(default="1000", pattern=r"^\d{1,15}(\.\d{1,4})?$")


class CashParameters(ProfitParameters):
    due_within_days: int = Field(default=30, ge=1, le=365)
    slow_stock_days: int = Field(default=90, ge=1, le=730)
