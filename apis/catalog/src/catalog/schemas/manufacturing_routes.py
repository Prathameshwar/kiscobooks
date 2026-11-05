"""Typed sequential routes and exact, bounded, nonexecuting time definitions."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Literal

from billing_platform.exact import exact_decimal
from billing_platform.listing import ListQuery
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from catalog.schemas.classification import (
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)
from catalog.schemas.manufacturing_operations import readable_text
from catalog.schemas.units import ExpectedVersion

ExactNumber = Annotated[Decimal, BeforeValidator(exact_decimal, json_schema_input_type=str)]
TimeBasis = Literal["PER_OUTPUT_UNIT", "PER_BATCH"]


class RouteCreate(MasterInput):
    pass


class RouteUpdate(MasterUpdate):
    pass


class RouteListItem(MasterListItem):
    pass


class RouteDetail(RouteListItem, DetailFields):
    pass


class RouteQuery(MasterQuery):
    pass


class RouteStepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID | None = None
    sequence: int = Field(strict=True, ge=1, le=50)
    operation_revision_id: uuid.UUID
    setup_minutes: ExactNumber = Field(default=Decimal("0"), ge=0)
    run_minutes: ExactNumber = Field(default=Decimal("0"), ge=0)
    lead_time_minutes: ExactNumber = Field(default=Decimal("0"), ge=0)
    time_basis: TimeBasis = "PER_OUTPUT_UNIT"
    quantity_basis: ExactNumber = Field(default=Decimal("1"), gt=0)

    @field_validator("id", "operation_revision_id")
    @classmethod
    def real_reference(cls, value: uuid.UUID | None) -> uuid.UUID | None:
        if value is not None and value.int == 0:
            raise ValueError("a real route-step reference is required")
        return value


def ordered_steps(value: tuple[RouteStepInput, ...] | None) -> tuple[RouteStepInput, ...] | None:
    if value is not None:
        if tuple(step.sequence for step in value) != tuple(range(1, len(value) + 1)):
            raise ValueError("route steps must be in contiguous sequential order")
        ids = [step.id for step in value if step.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("route step identities must be unique")
    return value


class RouteRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specification: str = Field(min_length=1, max_length=2000)
    change_reason: str = Field(min_length=1, max_length=500)
    steps: tuple[RouteStepInput, ...] = Field(default=(), max_length=50)
    _text = field_validator("specification", "change_reason")(readable_text)
    _steps = field_validator("steps")(ordered_steps)


class RouteRevisionUpdate(ExpectedVersion):
    specification: str | None = Field(default=None, min_length=1, max_length=2000)
    change_reason: str | None = Field(default=None, min_length=1, max_length=500)
    steps: tuple[RouteStepInput, ...] | None = Field(default=None, max_length=50)
    _text = field_validator("specification", "change_reason")(readable_text)
    _steps = field_validator("steps")(ordered_steps)

    @model_validator(mode="after")
    def supplied_fields_cannot_be_null(self) -> "RouteRevisionUpdate":
        if any(getattr(self, key) is None for key in self.model_fields_set - {"expected_version"}):
            raise ValueError("route text and step set cannot be cleared with null")
        return self


class RouteRevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    route_id: uuid.UUID | None = None
    revision: int | None = None
    row_version: int | None = None
    status: Literal["DRAFT", "PUBLISHED", "RETIRED"] | None = None
    published_at: dt.datetime | None = None
    step_count: int | None = None


class RouteRevisionDetail(RouteRevisionListItem, DetailFields):
    specification: str | None = None
    change_reason: str | None = None


class RouteRevisionQuery(ListQuery):
    published: bool | None = None
    status: Literal["DRAFT", "PUBLISHED", "RETIRED"] | None = None


class RouteStepListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    revision_id: uuid.UUID | None = None
    sequence: int | None = None
    operation_revision_id: uuid.UUID | None = None
    setup_minutes: Decimal | None = None
    run_minutes: Decimal | None = None
    lead_time_minutes: Decimal | None = None
    time_basis: TimeBasis | None = None
    quantity_basis: Decimal | None = None


class RouteStepQuery(ListQuery):
    pass


class OperationReferenceQuery(ListQuery):
    value: uuid.UUID | None = None


class OperationRevisionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    operation_id: uuid.UUID
    code: str
    name: str
    revision: int
    status: Literal["DRAFT", "PUBLISHED", "RETIRED"]
    is_active: bool
