"""Pydantic schemas for template assignments and layout resolution.

``voucher_kind`` is the shared voucher vocabulary (docs/vouchers-plan.md); this service
validates its shape and the renderer's caller supplies it. Resolution answers one
question — "which layout does this document print on?" — and returns the layout, so it
is a read with a request body, not a mutation.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from design.schemas.canvas import CanvasDefinition

VoucherKind = Field(min_length=1, max_length=50, pattern=r"^[A-Z][A-Z0-9_]{0,49}$")
CurrencyCode = Field(default=None, min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
TaxCategory = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voucher_kind: str = VoucherKind
    template_id: uuid.UUID
    voucher_type_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    currency_code: str | None = CurrencyCode
    customer_tax_category: str | None = TaxCategory
    specific_version_id: uuid.UUID | None = None
    priority: int = Field(default=100, ge=1, le=1000)


class AssignmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int | None = Field(default=None, ge=1, le=1000)
    is_active: bool | None = None


class AssignmentItem(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    voucher_kind: str
    voucher_type_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    currency_code: str | None = None
    customer_tax_category: str | None = None
    template_id: uuid.UUID
    specific_version_id: uuid.UUID | None = None
    priority: int
    is_active: bool
    created_at: dt.datetime


class ResolveTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voucher_kind: str = VoucherKind
    voucher_type_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    currency_code: str | None = CurrencyCode
    customer_tax_category: str | None = TaxCategory


class ResolveTemplateResponse(BaseModel):
    """The resolved layout, and the rule that chose it.

    ``assignment_rule_id`` is ``None`` when no rule matched and the company's single
    published template was used instead — which is the difference between "configured"
    and "defaulted", and an operator needs to see it.
    """

    model_config = ConfigDict(extra="forbid")

    template_id: uuid.UUID
    template_code: str
    template_name: str
    version_id: uuid.UUID
    version_number: int
    layout_digest: str
    layout_definition: CanvasDefinition
    assignment_rule_id: uuid.UUID | None = None
