"""Company transaction-currency controls."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class CurrencyAllowanceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool
    expected_version: int | None = Field(default=None, strict=True, ge=1)


class CurrencyAllowanceView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    currency_code: str
    is_active: bool
    row_version: int


class CompanyCurrenciesView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_currency: str
    allowances: list[CurrencyAllowanceView]
