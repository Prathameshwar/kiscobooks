"""Checkout controls and drawer accountability inputs."""

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from billing_platform.exact import exact_decimal
from pydantic import BeforeValidator, Field, WithJsonSchema

from vouchers.schemas.configuration import Contract

Money = Annotated[
    Decimal,
    BeforeValidator(exact_decimal),
    WithJsonSchema({"type": "string"}, mode="validation"),
    Field(ge=0, max_digits=19, decimal_places=4, allow_inf_nan=False),
]


class OutletCreate(Contract):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=160)


class CounterCreate(Contract):
    outlet_id: uuid.UUID
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=160)


class OperatorCreate(Contract):
    user_id: uuid.UUID


class OperatorStatusUpdate(Contract):
    expected_version: int = Field(strict=True, ge=1)
    status: Literal["ACTIVE", "INACTIVE"]
    reason: str = Field(min_length=3, max_length=500)


class CounterOperatorDetail(Contract):
    id: uuid.UUID
    company_id: uuid.UUID
    counter_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    row_version: int


class MasterStatusUpdate(Contract):
    expected_version: int = Field(strict=True, ge=1)
    status: Literal["ACTIVE", "INACTIVE"]
    reason: str = Field(min_length=3, max_length=500)


class SessionOpen(Contract):
    counter_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    opening_cash: Money


class CashMovement(Contract):
    expected_version: int = Field(strict=True, ge=1)
    event_key: uuid.UUID
    source_voucher_id: uuid.UUID
    source_revision_id: uuid.UUID
    direction: Literal["IN", "OUT"]
    amount: Money = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


class SessionClose(Contract):
    expected_version: int = Field(strict=True, ge=1)
    counted_cash: Money
    reason: str | None = Field(default=None, max_length=500)


class CounterMasterDetail(Contract):
    id: uuid.UUID
    company_id: uuid.UUID
    code: str
    name: str
    status: str
    row_version: int
    outlet_id: uuid.UUID | None = None


class CounterSessionDetail(Contract):
    id: uuid.UUID
    company_id: uuid.UUID
    counter_id: uuid.UUID
    status: Literal["OPEN", "CLOSED"]
    currency: str
    opening_cash: Decimal
    expected_cash: Decimal
    counted_cash: Decimal | None
    variance: Decimal | None
    opened_by: uuid.UUID
    closed_by: uuid.UUID | None
    row_version: int
