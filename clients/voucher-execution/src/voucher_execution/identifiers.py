"""Canonical physical identifier input shared by admission and the stock owner."""

import unicodedata
from typing import Literal, Self

from billing_platform.errors import ValidationFailedError
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class IdentifierRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier_type: Literal["SERIAL", "IMEI"]
    namespace_rule: Literal["COMPANY", "MANUFACTURER_SKU"]
    min_count: int = Field(ge=0, le=8, strict=True)
    max_count: int = Field(ge=1, le=8, strict=True)
    requires_slot: StrictBool

    @model_validator(mode="after")
    def counts(self) -> Self:
        if self.min_count > self.max_count or (self.max_count > 1 and not self.requires_slot):
            raise ValueError("identifier counts and slot requirements are inconsistent")
        return self


class IdentifierInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier_type: Literal["SERIAL", "IMEI"]
    slot: int = Field(default=1, ge=1, le=8, strict=True)
    value: str = Field(min_length=1, max_length=120)


def normalized(value: str, *, maximum: int = 120) -> str:
    text = unicodedata.normalize("NFKC", value).strip()
    if (
        not text
        or len(text) > maximum
        or any(unicodedata.category(char).startswith("C") for char in text)
    ):
        raise ValidationFailedError(
            "identifier must contain printable text within its allowed length"
        )
    result = text.casefold()
    if len(result) > maximum:
        raise ValidationFailedError("normalized identifier exceeds its allowed length")
    return result


def validate_identifier_inputs(
    requirements: list[IdentifierRequirement], values: list[IdentifierInput]
) -> list[tuple[IdentifierInput, str]]:
    if not requirements or len({row.identifier_type for row in requirements}) != len(requirements):
        raise ValidationFailedError("a complete published identifier profile is required")
    rules = {row.identifier_type: row for row in requirements}
    slots: set[tuple[str, int]] = set()
    seen: set[tuple[str, str]] = set()
    result = []
    for value in values:
        rule = rules.get(value.identifier_type)
        if rule is None:
            raise ValidationFailedError("identifier type is not allowed by the published profile")
        slot = value.identifier_type, value.slot
        key = normalized(value.value)
        if value.identifier_type == "IMEI":
            if len(key) != 15 or not key.isascii() or not key.isdigit():
                raise ValidationFailedError("IMEI must contain exactly 15 digits")
            checksum = sum(
                (n * 2 // 10 + n * 2 % 10) if i % 2 else n for i, n in enumerate(map(int, key))
            )
            if checksum % 10:
                raise ValidationFailedError("IMEI checksum is invalid")
        if slot in slots or (value.identifier_type, key) in seen:
            raise ValidationFailedError("duplicate identifier or slot in this physical unit")
        if value.slot > rule.max_count or (not rule.requires_slot and value.slot != 1):
            raise ValidationFailedError("identifier slot exceeds the published profile")
        slots.add(slot)
        seen.add((value.identifier_type, key))
        result.append((value, key))
    for rule in requirements:
        count = sum(value.identifier_type == rule.identifier_type for value in values)
        if not rule.min_count <= count <= rule.max_count:
            raise ValidationFailedError("identifier counts do not satisfy the published profile")
    return result
