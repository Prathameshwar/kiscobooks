"""Bounded Purchase starting recipes; executable calculation remains Accounting-owned."""

from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from voucher_execution.invoice import Value


class PurchaseCalculationStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=80)
    purpose: Literal["DISCOUNT", "FREIGHT", "PACKING", "INSURANCE", "HANDLING", "OTHER_CHARGE"]
    input_kind: Literal["FIXED", "PERCENT"] = "PERCENT"
    value: Value = Field(default=Decimal(0), ge=0)
    scope: Literal["INVOICE", "SELECTED_LINES"] = "INVOICE"
    amount_basis: Literal["NET_EXCL_TAX", "GROSS_INCL_TAX"] = "NET_EXCL_TAX"
    basis_recipe: Literal["ORIGINAL", "AFTER_DISCOUNTS", "AFTER_STEPS"] = "AFTER_DISCOUNTS"
    dependencies: tuple[str, ...] = Field(default=(), max_length=32)
    tax_treatment: Literal["ASSESSABLE", "NO_CHANGE"] = "ASSESSABLE"

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("calculation step name cannot be blank")
        return value

    @model_validator(mode="after")
    def supported(self) -> Self:
        if self.input_kind == "PERCENT" and self.value > 100:
            raise ValueError("percentage must be between zero and 100")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("calculation dependencies must be distinct")
        if self.basis_recipe != "AFTER_STEPS" and self.dependencies:
            raise ValueError("named dependencies require the after-selected-steps basis")
        if self.basis_recipe == "AFTER_STEPS" and not self.dependencies:
            raise ValueError("select at least one preceding calculation step")
        if self.amount_basis == "GROSS_INCL_TAX" and self.tax_treatment != "ASSESSABLE":
            raise ValueError("tax-inclusive adjustments require assessable treatment")
        return self


class PurchaseCalculationPreset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=80)
    steps: tuple[PurchaseCalculationStep, ...] = Field(default=(), max_length=32)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        return PurchaseCalculationStep.name_not_blank(value)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        preceding: set[str] = set()
        for step in self.steps:
            if step.key in preceding or not set(step.dependencies) <= preceding:
                raise ValueError("steps require distinct keys and preceding dependencies")
            preceding.add(step.key)
        return self


class PurchaseCalculationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    presets: tuple[PurchaseCalculationPreset, ...] = Field(default=(), max_length=20)
    default_preset: str | None = None

    @model_validator(mode="after")
    def defaults(self) -> Self:
        keys = {preset.key for preset in self.presets}
        if len(keys) != len(self.presets):
            raise ValueError("calculation preset keys must be distinct")
        if len({preset.name.casefold() for preset in self.presets}) != len(self.presets):
            raise ValueError("calculation preset names must be distinct")
        if self.default_preset is not None and self.default_preset not in keys:
            raise ValueError("default calculation preset must exist")
        return self
