"""Closed company-setup command and bounded packaged unit definitions."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from catalog.schemas.units import PackTypeInput, UnitCreate


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UnitDefaultsInput(ClosedModel):
    expected_inventory: bool | None = Field(default=None, strict=True)


class StarterUnit(UnitCreate):
    inventory: bool = False
    canonical_code: str
    numerator: int = Field(ge=1, le=2**63 - 1, strict=True)
    denominator: int = Field(ge=1, le=2**63 - 1, strict=True)


class UnitStarterPack(ClosedModel):
    version: str = Field(pattern=r"^[A-Z0-9_]{1,40}$")
    units: list[StarterUnit] = Field(min_length=1, max_length=64)
    packs: list[PackTypeInput] = Field(max_length=32)

    @model_validator(mode="after")
    def closed_roots(self) -> UnitStarterPack:
        units = {row.code: row for row in self.units}
        if len(units) != len(self.units) or len({row.code for row in self.packs}) != len(
            self.packs
        ):
            raise ValueError("starter codes must be unique")
        for row in self.units:
            root = units.get(row.canonical_code)
            if (
                root is None
                or root.code != root.canonical_code
                or root.numerator != 1
                or root.denominator != 1
                or root.dimension != row.dimension
                or (root.inventory and not row.inventory)
            ):
                raise ValueError("starter conversions require compatible declared roots")
        return self


class UnitDefaultsResult(ClosedModel):
    company_id: uuid.UUID
    pack_version: str
    status: Literal["READY", "NOT_APPLICABLE"]
    inventory_enabled: bool
    units_created: int = Field(default=0, ge=0)
    conversions_created: int = Field(default=0, ge=0)
    packs_created: int = Field(default=0, ge=0)
    preserved_records: int = Field(default=0, ge=0)
    notices: list[str] = Field(default_factory=list, max_length=64)
