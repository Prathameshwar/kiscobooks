"""Pydantic schemas for invoice templates.

``status`` is deliberately **not** writable here. A template becomes ``PUBLISHED`` by
publishing a version and ``ARCHIVED`` by being deleted; letting a client set the column
would mark a template live with no layout behind it (docs/invoice-design.md §5.1).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from design.schemas.canvas import CanvasDefinition

PaperSize = Literal["A4", "LETTER", "A5", "THERMAL_80MM", "THERMAL_58MM", "CUSTOM"]
Orientation = Literal["PORTRAIT", "LANDSCAPE"]
MeasureUnit = Literal["mm", "in", "pt", "px"]
#: Whether a design's lines are products, accounts/expenses, or both (designer plan D2).
LineProfile = Literal["ITEMS", "ACCOUNTS", "MIXED"]
VoucherKindName = Annotated[
    str, Field(min_length=1, max_length=50, pattern=r"^[A-Z][A-Z0-9_]{0,49}$")
]

#: Page geometry is a measurement, so it is ``Decimal`` end to end — the column is
#: ``DECIMAL(19,4)`` and a float round-trip would silently re-scale it (CLAUDE.md §4).
PageMeasure = Decimal


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$")
    description: str | None = Field(default=None, max_length=500)
    paper_size: PaperSize = "A4"
    page_orientation: Orientation = "PORTRAIT"
    page_width_mm: PageMeasure | None = Field(default=None, gt=0, le=2000)
    page_height_mm: PageMeasure | None = Field(default=None, gt=0, le=2000)
    unit_of_measure: MeasureUnit = "mm"
    #: Tenant-wide house style. Requires tenant-scoped authority, not company authority.
    is_tenant_wide: bool = False
    initial_canvas: CanvasDefinition | None = None
    #: What the design is for. Optional: an unstated design may print for any kind.
    voucher_kind: VoucherKindName | None = None
    line_profile: LineProfile | None = None

    @model_validator(mode="after")
    def custom_paper_is_measured(self) -> TemplateCreate:
        measured = self.page_width_mm is not None and self.page_height_mm is not None
        if self.paper_size == "CUSTOM" and not measured:
            raise ValueError("a CUSTOM paper size requires both page_width_mm and page_height_mm")
        if self.line_profile is not None and self.voucher_kind is None:
            raise ValueError("a line profile belongs to a voucher kind; name the kind too")
        return self


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    paper_size: PaperSize | None = None
    page_orientation: Orientation | None = None
    page_width_mm: PageMeasure | None = Field(default=None, gt=0, le=2000)
    page_height_mm: PageMeasure | None = Field(default=None, gt=0, le=2000)
    unit_of_measure: MeasureUnit | None = None
    voucher_kind: VoucherKindName | None = None
    line_profile: LineProfile | None = None


class TemplateCreated(BaseModel):
    """What creation returns: the template, and the version it created, if any.

    A created template is ``DRAFT`` with no live version, so ``current_version_id`` is
    null — the designer needs the id of the draft version it just saved, and making the
    client list versions to find it would be a worse contract.
    """

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    paper_size: str
    page_orientation: str
    page_width_mm: Decimal | None = None
    page_height_mm: Decimal | None = None
    unit_of_measure: str
    status: str
    is_system: bool
    voucher_kind: str | None = None
    line_profile: str | None = None
    current_version_id: uuid.UUID | None = None
    initial_version_id: uuid.UUID | None = None
    created_at: dt.datetime
    created_by: uuid.UUID | None = None
    updated_at: dt.datetime
    updated_by: uuid.UUID | None = None


class TemplateItem(BaseModel):
    """The lean list projection — no page geometry, no audit columns."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    code: str
    paper_size: str
    page_orientation: str
    status: str
    is_system: bool
    voucher_kind: str | None = None
    line_profile: str | None = None
    current_version_id: uuid.UUID | None = None
    updated_at: dt.datetime


class TemplateDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    paper_size: str
    page_orientation: str
    page_width_mm: Decimal | None = None
    page_height_mm: Decimal | None = None
    unit_of_measure: str
    status: str
    is_system: bool
    voucher_kind: str | None = None
    line_profile: str | None = None
    current_version_id: uuid.UUID | None = None
    created_at: dt.datetime
    created_by: uuid.UUID | None = None
    updated_at: dt.datetime
    updated_by: uuid.UUID | None = None
