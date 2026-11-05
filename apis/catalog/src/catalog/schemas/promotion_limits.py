"""Exact count strings and typed native promotion limit authoring contracts."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from billing_platform.exact import exact_decimal
from billing_platform.listing import ListQuery
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_serializer,
    model_validator,
)

from catalog.domain.promotion_limits import LimitIdentity
from catalog.schemas.classification import (
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)
from catalog.schemas.units import ExpectedVersion, UnitCreate

ScopeKind = Literal["CAMPAIGN", "PROMOTION", "PROGRAM"]
Metric = Literal["TOTAL_USES", "PER_CUSTOMER_USES", "PER_ORDER_USES", "REWARD_UNITS", "BUDGET"]
PeriodBasis = Literal["LIFETIME", "DAY", "MONTH", "YEAR", "ORDER"]


class LimitCreate(MasterInput):
    scope_kind: ScopeKind
    metric: Metric
    period_basis: PeriodBasis
    timezone: str = Field(min_length=1, max_length=64)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    unit_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def identity(self) -> Self:
        LimitIdentity(
            self.scope_kind,
            self.metric,
            self.period_basis,
            self.timezone,
            self.currency,
            self.unit_id,
        )
        return self


class LimitUpdate(MasterUpdate):
    scope_kind: ScopeKind | None = None
    metric: Metric | None = None
    period_basis: PeriodBasis | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    unit_id: uuid.UUID | None = None


class LimitListItem(MasterListItem):
    scope_kind: ScopeKind | None = None
    metric: Metric | None = None
    period_basis: PeriodBasis | None = None


class LimitDetail(LimitListItem, DetailFields):
    timezone: str | None = None
    currency: str | None = None
    unit_id: uuid.UUID | None = None


class LimitQuery(MasterQuery):
    scope_kind: ScopeKind | None = None
    metric: Metric | None = None


def count_input(value: Any) -> int:
    if (
        type(value) is not str
        or not value.isascii()
        or not value.isdigit()
        or len(value) > 19
        or not 1 <= int(value) <= 2**63 - 1
    ):
        raise ValueError("enter a positive signed-64-bit count as an exact string")
    return int(value)


def native_decimal(value: Any) -> Decimal:
    result = exact_decimal(value)
    if result <= 0:
        raise ValueError("cap must be positive")
    return result


CountInput = Annotated[int, BeforeValidator(count_input, json_schema_input_type=str)]
ExactCap = Annotated[Decimal, BeforeValidator(native_decimal, json_schema_input_type=str)]


class LimitRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maximum_count: CountInput | None = None
    maximum_quantity: ExactCap | None = None
    maximum_amount: ExactCap | None = None
    change_reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def cap(self) -> Self:
        if (
            sum(
                value is not None
                for value in (self.maximum_count, self.maximum_quantity, self.maximum_amount)
            )
            != 1
        ):
            raise ValueError("provide exactly one native count, quantity or budget cap")
        self.change_reason = UnitCreate.meaningful_label(self.change_reason)
        return self

    @field_serializer("maximum_count", when_used="json")
    def count_json(self, value: int | None) -> str | None:
        return str(value) if value is not None else None


class LimitRevisionUpdate(LimitRevisionInput, ExpectedVersion):
    pass


class LimitRevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    definition_id: uuid.UUID | None = None
    revision: int | None = None
    row_version: int | None = None
    published_at: dt.datetime | None = None
    maximum_count: int | None = None
    maximum_quantity: Decimal | None = None
    maximum_amount: Decimal | None = None

    @field_serializer("maximum_count", when_used="json")
    def count_json(self, value: int | None) -> str | None:
        return str(value) if value is not None else None


class LimitRevisionDetail(LimitRevisionListItem, DetailFields):
    change_reason: str | None = None
    published_source_version: int | None = None
    publication_generation: int | None = None
    complete: bool
    operational_ready: Literal[False] = False


class LimitRevisionQuery(ListQuery):
    published: bool | None = None
