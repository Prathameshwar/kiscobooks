"""Validated ISO materialization payloads; no permissions or tax policy here."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReferenceData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    name: str = Field(min_length=1, max_length=128)
    is_active: bool = Field(default=True, strict=True)

    @field_validator("*", mode="after")
    @classmethod
    def clean(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError("enter a valid value without control characters")
        return value


class CountryData(ReferenceData):
    kind: Literal["country"]
    code: str = Field(pattern=r"^[A-Z]{2}$")
    name: str = Field(min_length=1, max_length=100)
    iso3: str = Field(pattern=r"^[A-Z]{3}$")
    numeric_code: str = Field(pattern=r"^[0-9]{3}$")
    official_name: str = Field(min_length=1, max_length=200)
    default_currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    phone_prefix: str = Field(pattern=r"^\+[0-9]{1,7}$")
    subdivision_label: str = Field(min_length=1, max_length=60)


class StateData(ReferenceData):
    kind: Literal["state"]
    code: str = Field(pattern=r"^[A-Z]{2}-[A-Z0-9]{1,3}$")
    name: str = Field(min_length=1, max_length=100)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    subdivision_type: str = Field(min_length=1, max_length=60)
    tax_jurisdiction_code: str | None = Field(default=None, pattern=r"^[0-9]{2}$")

    @model_validator(mode="after")
    def parent(self) -> Self:
        if not self.code.startswith(self.country_code + "-"):
            raise ValueError("state code must start with the selected country code")
        if self.tax_jurisdiction_code is not None and self.country_code != "IN":
            raise ValueError("GST jurisdiction codes apply only to India")
        return self


class CurrencyData(ReferenceData):
    kind: Literal["currency"]
    code: str = Field(pattern=r"^[A-Z]{3}$")
    name: str = Field(min_length=1, max_length=100)
    numeric_code: str = Field(pattern=r"^[0-9]{3}$")
    symbol: str = Field(min_length=1, max_length=8)
    minor_unit: int = Field(strict=True, ge=0, le=4)
    major_unit_name: str = Field(min_length=1, max_length=40)
    minor_unit_name: str | None = Field(default=None, max_length=40)
    minor_unit_name_plural: str | None = Field(default=None, max_length=40)


class LanguageData(ReferenceData):
    kind: Literal["language"]
    code: str = Field(pattern=r"^[a-z]{2}$")
    iso3: str = Field(pattern=r"^[a-z]{3}$")
    native_name: str | None = Field(default=None, max_length=128)


CatalogData = Annotated[
    CountryData | StateData | CurrencyData | LanguageData, Field(discriminator="kind")
]
