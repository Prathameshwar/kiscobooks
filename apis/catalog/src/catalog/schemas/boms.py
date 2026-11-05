"""Typed, bounded single-level BOM authoring and non-posting preview contracts."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Literal

from billing_platform.exact import exact_decimal, exact_rate
from billing_platform.listing import ListQuery
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from catalog.domain.bom_definitions import BatchRule
from catalog.schemas.classification import (
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)
from catalog.schemas.manufacturing_operations import readable_text
from catalog.schemas.units import ExpectedVersion

Quantity = Annotated[Decimal, BeforeValidator(exact_decimal, json_schema_input_type=str)]
Rate = Annotated[Decimal, BeforeValidator(exact_rate, json_schema_input_type=str)]
OutputRole = Literal["PRIMARY", "CO_PRODUCT", "BY_PRODUCT", "SCRAP"]


def real_reference(value: uuid.UUID | None) -> uuid.UUID | None:
    if value is not None and value.int == 0:
        raise ValueError("a real BOM line reference is required")
    return value


class BomCreate(MasterInput):
    pass


class BomUpdate(MasterUpdate):
    pass


class BomListItem(MasterListItem):
    pass


class BomDetail(BomListItem, DetailFields):
    pass


class BomQuery(MasterQuery):
    pass


class LineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_key: uuid.UUID
    sequence: int = Field(strict=True, ge=1)
    item_id: uuid.UUID
    unit_revision_id: uuid.UUID | None = None

    _reference = field_validator("line_key", "item_id", "unit_revision_id")(real_reference)


class ComponentInput(LineInput):
    sequence: int = Field(strict=True, ge=1, le=1000)
    quantity: Quantity = Field(gt=0)
    basis: Literal["GROSS_INPUT", "NET_REQUIRED"] = "GROSS_INPUT"
    loss_fraction: Rate = Field(default=Decimal("0"), ge=0, lt=1)
    timing: Literal["PER_BASIS", "PER_RUN"] = "PER_BASIS"
    route_step_id: uuid.UUID | None = None
    _step_reference = field_validator("route_step_id")(real_reference)

    @model_validator(mode="after")
    def explicit_loss(self) -> "ComponentInput":
        if self.basis == "GROSS_INPUT" and self.loss_fraction:
            raise ValueError("gross input cannot also be grossed up for loss")
        return self


class OutputInput(LineInput):
    sequence: int = Field(strict=True, ge=1, le=100)
    nominal_quantity: Quantity = Field(gt=0)
    yield_fraction: Rate = Field(default=Decimal("1"), gt=0, le=1)
    role: OutputRole = "PRIMARY"


class BomDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specification: str = Field(min_length=1, max_length=2000)
    change_reason: str = Field(min_length=1, max_length=500)
    definition_date: dt.date = Field(ge=dt.date(1000, 1, 1))
    route_revision_id: uuid.UUID | None = None
    batch_minimum: Quantity | None = Field(default=None, gt=0)
    batch_maximum: Quantity | None = Field(default=None, gt=0)
    batch_multiple: Quantity | None = Field(default=None, gt=0)
    components: tuple[ComponentInput, ...] = Field(default=(), max_length=1000)
    outputs: tuple[OutputInput, ...] = Field(default=(), max_length=100)
    _text = field_validator("specification", "change_reason")(readable_text)
    _reference = field_validator("route_revision_id")(real_reference)

    @model_validator(mode="after")
    def coherent_definition(self) -> "BomDraftInput":
        BatchRule(self.batch_minimum, self.batch_maximum, self.batch_multiple)
        lines = (*self.components, *self.outputs)
        if len({row.line_key for row in lines}) != len(lines):
            raise ValueError("BOM line keys must be unique across components and outputs")
        for rows in (self.components, self.outputs):
            if tuple(row.sequence for row in rows) != tuple(range(1, len(rows) + 1)):
                raise ValueError("BOM lines must be in contiguous sequence")
        output_items = {row.item_id for row in self.outputs}
        if len(output_items) != len(self.outputs):
            raise ValueError("output SKUs must be distinct")
        if output_items & {row.item_id for row in self.components}:
            raise ValueError("a BOM cannot consume its own output")
        if sum(row.role == "PRIMARY" for row in self.outputs) > 1:
            raise ValueError("a BOM permits one primary output")
        if self.route_revision_id is None and any(row.route_step_id for row in self.components):
            raise ValueError("component route steps require a pinned route revision")
        return self


class BomDraftUpdate(BomDraftInput, ExpectedVersion):
    """Full reviewed aggregate replacement, including both complete child collections."""


class BomDraftListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    bom_id: uuid.UUID | None = None
    draft_number: int | None = None
    row_version: int | None = None
    status: Literal["DRAFT", "PUBLISHED"] | None = None
    published_revision_id: uuid.UUID | None = None
    definition_date: dt.date | None = None
    component_count: int | None = None
    output_count: int | None = None


class BomDraftDetail(BomDraftListItem, DetailFields):
    specification: str | None = None
    change_reason: str | None = None
    route_revision_id: uuid.UUID | None = None
    batch_minimum: Decimal | None = None
    batch_maximum: Decimal | None = None
    batch_multiple: Decimal | None = None


class BomRevisionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    bom_id: uuid.UUID | None = None
    revision: int | None = None
    row_version: int | None = None
    status: Literal["PUBLISHED", "RETIRED"] | None = None
    published_at: dt.datetime | None = None
    definition_date: dt.date | None = None
    component_count: int | None = None
    output_count: int | None = None


class BomRevisionDetail(BomRevisionListItem, DetailFields):
    draft_id: uuid.UUID | None = None
    specification: str | None = None
    change_reason: str | None = None
    route_revision_id: uuid.UUID | None = None
    batch_minimum: Decimal | None = None
    batch_maximum: Decimal | None = None
    batch_multiple: Decimal | None = None
    policy_generation: int
    source_version: int | None = None
    content_sha256: str | None = None
    # Generated dependency evidence is retained separately from this lean detail projection.


class ComponentListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    draft_id: uuid.UUID | None = None
    revision_id: uuid.UUID | None = None
    line_key: uuid.UUID | None = None
    sequence: int | None = None
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    quantity: Decimal | None = None
    basis: Literal["GROSS_INPUT", "NET_REQUIRED"] | None = None
    loss_fraction: Decimal | None = None
    timing: Literal["PER_BASIS", "PER_RUN"] | None = None
    route_step_id: uuid.UUID | None = None


class OutputListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    draft_id: uuid.UUID | None = None
    revision_id: uuid.UUID | None = None
    line_key: uuid.UUID | None = None
    sequence: int | None = None
    item_id: uuid.UUID | None = None
    unit_revision_id: uuid.UUID | None = None
    nominal_quantity: Decimal | None = None
    yield_fraction: Decimal | None = None
    role: OutputRole | None = None


class BomHistoryQuery(ListQuery):
    status: Literal["DRAFT", "PUBLISHED", "RETIRED"] | None = None


class BomLineQuery(ListQuery):
    pass


class AssignmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bom_revision_id: uuid.UUID
    item_id: uuid.UUID
    warehouse_id: uuid.UUID | None = None
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))
    valid_to: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))
    change_reason: str = Field(min_length=1, max_length=500)
    _text = field_validator("change_reason")(readable_text)
    _reference = field_validator("bom_revision_id", "item_id", "warehouse_id")(real_reference)

    @model_validator(mode="after")
    def ordered_dates(self) -> "AssignmentInput":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("assignment end precedes its start")
        return self


class AssignmentUpdate(AssignmentInput, ExpectedVersion):
    pass


class AssignmentListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    bom_revision_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    is_active: bool | None = None
    row_version: int | None = None


class AssignmentDetail(AssignmentListItem, DetailFields):
    change_reason: str | None = None


class AssignmentQuery(ListQuery):
    bom_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    is_active: bool | None = None


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested_good_quantity: Quantity = Field(gt=0)
    run_count: int | None = Field(default=None, strict=True, ge=1, le=1000)
    run_quantities: tuple[Quantity, ...] | None = Field(default=None, min_length=1, max_length=1000)


class PreviewRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_key: uuid.UUID
    item_id: uuid.UUID
    required_quantity: Decimal
    base_quantity: Decimal


class PreviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_key: uuid.UUID
    item_id: uuid.UUID
    role: OutputRole
    expected_quantity: Decimal
    base_quantity: Decimal


class PreviewDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nominal_run_quantity: Decimal
    requirements: tuple[PreviewRequirement, ...]
    outputs: tuple[PreviewOutput, ...]
    operational_ready: Literal[False] = False


class AuthoringContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: uuid.UUID
    enabled: bool
    maximum_components: Literal[1000] = 1000
    maximum_outputs: Literal[100] = 100
    operational_ready: Literal[False] = False


class SelectionQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: uuid.UUID
    warehouse_id: uuid.UUID | None = None
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))


class SelectionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignment_id: uuid.UUID
    bom_revision_id: uuid.UUID
    operational_ready: Literal[False] = False


class BomReferenceQuery(ListQuery):
    value: uuid.UUID | None = None


class BomUnitQuery(BomReferenceQuery):
    item_id: uuid.UUID
    as_of: dt.date = Field(ge=dt.date(1000, 1, 1))


class BomRevisionOptionsQuery(BomReferenceQuery):
    bom_id: uuid.UUID | None = None


class BomReferenceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    parent_id: uuid.UUID
    code: str
    name: str
    revision: int


class BomUnitOption(BomReferenceOption):
    unit_id: uuid.UUID
    valid_from: dt.date
    valid_to: dt.date | None


class BomStoredReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    source: Literal["goods", "units", "routes", "revisions"]
    parent_id: uuid.UUID | None = None
    code: str
    name: str
    revision: int | None = None
    step_count: int | None = None
