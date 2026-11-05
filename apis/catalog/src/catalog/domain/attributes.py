"""Native attribute values and template rules; descriptive custom fields are separate."""

from __future__ import annotations

import datetime as dt
import hashlib
import unicodedata
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from billing_platform.errors import ValidationFailedError
from billing_platform.exact import RationalConversion, exact_decimal
from billing_platform.idempotency import canonical_json

VALUE_TYPES = frozenset({"TEXT", "INTEGER", "DECIMAL", "BOOLEAN", "DATE"})
DIMENSIONS = frozenset({"COUNT", "MASS", "VOLUME", "LENGTH", "AREA", "TIME", "JOB"})


@dataclass(frozen=True, slots=True)
class DefinitionRules:
    value_type: str
    measurement_dimension: str | None
    is_variant_capable: bool
    is_active: bool = True

    def __post_init__(self) -> None:
        if self.value_type not in VALUE_TYPES or any(
            type(flag) is not bool for flag in (self.is_variant_capable, self.is_active)
        ):
            raise ValidationFailedError("invalid native attribute definition")
        if self.measurement_dimension is not None and (
            self.measurement_dimension not in DIMENSIONS
            or self.value_type not in {"INTEGER", "DECIMAL"}
        ):
            raise ValidationFailedError(
                "only numeric attributes can have supported measurement dimensions"
            )


@dataclass(frozen=True, slots=True)
class AttributeValue:
    value_type: str
    value: Any
    unit_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        valid = False
        if self.value_type == "TEXT":
            valid = (
                isinstance(self.value, str)
                and 0 < len(self.value) <= 200
                and bool(self.value.strip())
                and not any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in self.value)
            )
        elif self.value_type == "INTEGER":
            valid = type(self.value) is int and -(2**63) <= self.value < 2**63
        elif self.value_type == "DECIMAL":
            try:
                object.__setattr__(self, "value", exact_decimal(self.value))
                valid = True
            except ValueError:
                valid = False
        elif self.value_type == "BOOLEAN":
            valid = type(self.value) is bool
        elif self.value_type == "DATE":
            valid = type(self.value) is dt.date and self.value >= dt.date(1000, 1, 1)
        if not valid or (
            self.unit_id is not None
            and (
                not isinstance(self.unit_id, uuid.UUID)
                or self.unit_id.int == 0
                or self.value_type not in {"INTEGER", "DECIMAL"}
            )
        ):
            raise ValidationFailedError("invalid typed attribute value")

    def validate_definition(self, definition: DefinitionRules) -> None:
        if self.value_type != definition.value_type or (self.unit_id is None) != (
            definition.measurement_dimension is None
        ):
            raise ValidationFailedError("attribute value does not match its definition")

    def canonical(
        self,
        *,
        canonical_unit_id: uuid.UUID | None = None,
        conversion: RationalConversion | None = None,
    ) -> tuple[bytes, bytes]:
        if (self.unit_id is None) != (canonical_unit_id is None) or (self.unit_id is None) != (
            conversion is None
        ):
            raise ValidationFailedError(
                "measured attribute equality requires canonical unit evidence"
            )
        value: Any = self.value
        if self.value_type == "TEXT":
            value = unicodedata.normalize("NFKC", value).strip().casefold()
        elif self.value_type in {"INTEGER", "DECIMAL"}:
            rational = conversion.apply(value) if conversion is not None else Fraction(value)
            value = {"numerator": str(rational.numerator), "denominator": str(rational.denominator)}
        elif self.value_type == "DATE":
            value = value.isoformat()
        content = canonical_json(
            {
                "version": 1,
                "type": self.value_type,
                "value": value,
                "unit": str(canonical_unit_id) if canonical_unit_id else None,
            }
        )
        if len(content) > 1024:
            raise ValidationFailedError("canonical attribute value exceeds storage bounds")
        return hashlib.sha256(content).digest(), content


@dataclass(frozen=True, slots=True)
class MemberRule:
    definition_id: uuid.UUID
    position: int
    is_required: bool
    allow_variant_axis: bool

    def __post_init__(self) -> None:
        if (
            self.definition_id.int == 0
            or type(self.position) is not int
            or not 0 <= self.position < 128
            or any(type(flag) is not bool for flag in (self.is_required, self.allow_variant_axis))
        ):
            raise ValidationFailedError("invalid attribute template member")


def validate_members(
    members: tuple[MemberRule, ...],
    definitions: Mapping[uuid.UUID, DefinitionRules],
    *,
    allow_empty: bool = False,
) -> None:
    if len(members) > 128 or (not members and not allow_empty):
        raise ValidationFailedError("attribute template requires between one and 128 members")
    if len({member.definition_id for member in members}) != len(members) or len(
        {member.position for member in members}
    ) != len(members):
        raise ValidationFailedError("attribute template definitions and positions must be unique")
    for member in members:
        definition = definitions.get(member.definition_id)
        if definition is None or not definition.is_active:
            raise ValidationFailedError("attribute template requires active definitions")
        if member.allow_variant_axis and not definition.is_variant_capable:
            raise ValidationFailedError(
                "template cannot enable variants on an ineligible definition"
            )
