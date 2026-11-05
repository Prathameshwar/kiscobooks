"""Exact decimal inputs and server-derived INR/USD commercial previews."""

import datetime as dt
import uuid
from decimal import ROUND_CEILING, Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, computed_field, field_validator, model_validator

from identity.schemas.base import StrictModel

Money = Annotated[
    Decimal,
    Field(ge=0, le=Decimal("999999999.9999"), max_digits=19, decimal_places=4, allow_inf_nan=False),
]
Category = Literal["platform", "whatsapp", "sms", "email", "llm", "document"]
Unit = Literal["none", "messages", "segments", "emails", "tokens", "pages"]


class PlatformPriceInput(StrictModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9-]{1,39}$")
    name: str = Field(min_length=1, max_length=100)
    category: Category
    description: str = Field(default="", max_length=1000)
    term_months: Literal[1, 12, 36]
    unit: Unit
    monthly_fee: Annotated[
        Decimal, Field(ge=0, le=Decimal("999999999.99"), max_digits=19, decimal_places=2)
    ]
    unit_price: Money = Decimal("0")
    output_unit_price: Money = Decimal("0")
    tax_percent: Annotated[Decimal, Field(ge=0, le=100, max_digits=7, decimal_places=4)] = Decimal(
        "18"
    )
    fx_inr_per_usd: Annotated[Decimal, Field(ge=1, le=1000, max_digits=8, decimal_places=4)] = (
        Decimal("94.8228")
    )
    provider: str = Field(default="", max_length=60)
    model: str = Field(default="", max_length=100)
    is_active: bool = True

    @field_validator("name", "description", "provider", "model")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = value.strip()
        if any(ord(char) < 32 for char in value):
            raise ValueError("control characters are not allowed")
        return value

    @model_validator(mode="after")
    def consistent_units(self) -> Self:
        if not self.name:
            raise ValueError("enter a price name")
        expected = {
            "platform": "none",
            "whatsapp": "messages",
            "sms": "segments",
            "email": "emails",
            "llm": "tokens",
            "document": "pages",
        }
        if self.unit != expected[self.category]:
            raise ValueError("usage unit must match the offering category")
        if self.category == "platform":
            if (
                self.term_months not in (12, 36)
                or self.unit_price
                or self.output_unit_price
                or not self.monthly_fee
            ):
                raise ValueError(
                    "platform plans need a 12/36 month term, a positive fee and no usage charges"
                )
        elif self.term_months != 1 or self.unit_price <= 0:
            raise ValueError("add-ons need a one-month term and positive usage pricing")
        if self.category == "llm":
            if not self.provider or not self.model or self.output_unit_price <= 0:
                raise ValueError(
                    "LLM prices need provider, model and separate input/output token rates"
                )
        elif self.output_unit_price:
            raise ValueError("output token pricing applies only to LLM offerings")
        return self


class PlatformPriceUpdate(PlatformPriceInput):
    expected_version: int = Field(ge=1, le=2147483646)


class PlatformPriceLifecycle(StrictModel):
    expected_version: int = Field(ge=1, le=2147483646)


class PriceCurrency(StrictModel):
    currency: Literal["INR", "USD"]
    monthly_fee: Decimal
    unit_price: Decimal
    output_unit_price: Decimal
    term_net: Decimal
    term_tax: Decimal
    term_total: Decimal


class PlatformPriceDetail(PlatformPriceInput):
    id: uuid.UUID
    version: int
    deleted_at: dt.datetime | None
    prices: list[PriceCurrency]


class PlatformPriceItem(StrictModel):
    id: uuid.UUID
    code: str
    name: str
    category: Category
    term_months: int
    unit: Unit
    monthly_fee: Decimal
    unit_price: Decimal
    output_unit_price: Decimal
    fx_inr_per_usd: Decimal
    is_active: bool
    version: int
    deleted_at: dt.datetime | None

    @computed_field  # type: ignore[prop-decorator]  # Pydantic property support exceeds mypy's.
    @property
    def usd_monthly_fee(self) -> Decimal:
        return usd_amount(self.monthly_fee, self.fx_inr_per_usd, "0.01")

    @computed_field  # type: ignore[prop-decorator]  # Pydantic property support exceeds mypy's.
    @property
    def usd_unit_price(self) -> Decimal:
        return usd_amount(self.unit_price, self.fx_inr_per_usd, "0.0001")


class PlatformPriceRevisionItem(StrictModel):
    id: uuid.UUID
    version: int
    snapshot: PlatformPriceDetail
    created_at: dt.datetime


def usd_amount(value: Decimal, fx: Decimal, quantum: str) -> Decimal:
    return (value / fx * Decimal("1.20")).quantize(Decimal(quantum), rounding=ROUND_CEILING)
