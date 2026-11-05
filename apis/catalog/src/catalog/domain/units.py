"""Native quantity and unit rules; no stock ledger or pricing derivation.

Unit dimensions and item-specific packs are separate. Every persisted quantity
must satisfy its input unit and binding constraints before exact conversion.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from billing_platform.errors import ValidationFailedError
from billing_platform.exact import DecimalInput, RationalConversion, exact_decimal
from billing_platform.money import MoneyError


@dataclass(frozen=True, slots=True)
class QuantityRule:
    decimal_places: int
    increment: Decimal

    def __post_init__(self) -> None:
        step = exact_decimal(self.increment, decimal_places=self.decimal_places)
        if step <= 0:
            raise ValidationFailedError("quantity increment must be positive")
        object.__setattr__(self, "increment", step)

    def validate(self, value: DecimalInput) -> Decimal:
        return exact_decimal(value, decimal_places=self.decimal_places, increment=self.increment)


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    id: uuid.UUID
    company_id: uuid.UUID
    dimension: str
    quantity: QuantityRule

    def __post_init__(self) -> None:
        if self.dimension not in {"COUNT", "MASS", "VOLUME", "LENGTH", "AREA", "TIME", "JOB"}:
            raise ValidationFailedError("unsupported unit dimension")
        if self.id.int == 0 or self.company_id.int == 0:
            raise ValidationFailedError("unit requires real company and unit identifiers")


@dataclass(frozen=True, slots=True)
class CanonicalRelation:
    unit: UnitDefinition
    canonical: UnitDefinition
    ratio: RationalConversion

    def __post_init__(self) -> None:
        if self.unit.company_id != self.canonical.company_id:
            raise ValidationFailedError("unit conversion must stay in the same company")
        if self.unit.dimension != self.canonical.dimension:
            raise ValidationFailedError("global unit conversion requires the same dimension")
        if self.unit.id == self.canonical.id and self.ratio != RationalConversion(1, 1):
            raise ValidationFailedError("canonical unit must have identity conversion")


def validate_canonical_relations(relations: tuple[CanonicalRelation, ...]) -> None:
    """One direct relation per unit; canonical roots cannot form chains or cycles."""
    by_unit = {relation.unit.id: relation for relation in relations}
    if len(by_unit) != len(relations):
        raise ValidationFailedError("a unit has multiple canonical relations")
    for relation in relations:
        root = by_unit.get(relation.canonical.id)
        if root is None or root.unit.id != root.canonical.id:
            raise ValidationFailedError(
                "canonical relations must point directly to a declared root"
            )
        if root.unit != relation.canonical:
            raise ValidationFailedError("canonical unit definitions disagree")


@dataclass(frozen=True, slots=True)
class FixedBinding:
    id: uuid.UUID
    unit: UnitDefinition
    base: UnitDefinition
    ratio: RationalConversion
    quantity: QuantityRule
    fractional_entry: bool = True
    serialized_base: bool = False

    def __post_init__(self) -> None:
        if self.unit.company_id != self.base.company_id:
            raise ValidationFailedError("item unit binding must stay in the same company")
        if self.unit.dimension != self.base.dimension:
            raise ValidationFailedError("cross-dimension item quantities require measured mode")
        if self.quantity.decimal_places > self.unit.quantity.decimal_places:
            raise ValidationFailedError("item precision cannot exceed unit precision")
        if self.serialized_base and (
            self.base.dimension != "COUNT" or self.base.quantity.decimal_places != 0
        ):
            raise ValidationFailedError("serialized stock requires a whole-count base unit")

    def entered(self, value: DecimalInput) -> Decimal:
        result = self.quantity.validate(self.unit.quantity.validate(value))
        if result < 0:
            raise ValidationFailedError("entered quantity cannot be negative")
        if not self.fractional_entry and result != result.to_integral_value():
            raise ValidationFailedError("fractional pack entry is disabled")
        return result

    def convert(self, value: DecimalInput) -> Decimal:
        result = storage_quantity(self.ratio.apply(self.entered(value)))
        self.base.quantity.validate(result)
        return result


def storage_quantity(value: Fraction) -> Decimal:
    """Check final quantities without stored-ratio bounds on intermediate arithmetic."""
    scaled = value * 10000
    if scaled.denominator != 1:
        raise MoneyError("converted quantity is not exactly representable in storage")
    number = scaled.numerator
    return exact_decimal(Decimal((int(number < 0), tuple(map(int, str(abs(number)))), -4)))


def compound_quantity(parts: tuple[tuple[FixedBinding, DecimalInput], ...]) -> Decimal:
    """Structured 2 boxes + 3 pieces, never the ambiguous decimal '2.3 boxes'."""
    if not 1 <= len(parts) <= 8 or len({binding.id for binding, _ in parts}) != len(parts):
        raise ValidationFailedError("compound entry requires one to eight distinct bindings")
    base = parts[0][0].base
    if any(binding.base != base for binding, _ in parts):
        raise ValidationFailedError("compound components must share the same base unit definition")
    # Each component must itself be valid; fractional residues cannot cancel out.
    total = sum((Fraction(binding.convert(value)) for binding, value in parts), Fraction())
    result = storage_quantity(total)
    base.quantity.validate(result)
    return result


@dataclass(frozen=True, slots=True)
class CompoundComponent:
    """One row of a compound unit's *multiplicative* decomposition.

    A component names a child unit and a positive quantity — ``1 case = 12 x bag``
    is a single component ``(bag, 12)``; ``1 case = 12 x 5kg`` is two components
    ``(bag, 12)`` then ``(kg, 5)`` walked in ``ordinal`` order.

    Distinct from :func:`compound_quantity`, which is the structured *additive*
    entry (``2 boxes + 3 pieces``); this one is the multiplicative structure of
    a compound unit's definition.
    """

    ordinal: int
    child_unit: UnitDefinition
    quantity: Decimal
    child_is_active: bool

    def __post_init__(self) -> None:
        if self.ordinal < 1:
            raise ValidationFailedError("compound component ordinal must be positive")
        if self.quantity <= 0:
            raise ValidationFailedError("compound component quantity must be positive")


def compound_factor(parent: UnitDefinition, components: tuple[CompoundComponent, ...]) -> Fraction:
    """Product of the components — the exact quantity of the smallest child in one parent.

    Refuses a component whose ``child_unit`` is inactive: a compound unit is a
    dated definition, and using an inactive child would let a document silently
    reprice against a retired unit. All arithmetic is exact rationals; the
    caller decides how to fold this into a full conversion chain.
    """
    if not components:
        raise ValidationFailedError("compound unit must have at least one component")
    seen: set[int] = set()
    total = Fraction(1)
    for component in sorted(components, key=lambda c: c.ordinal):
        if component.ordinal in seen:
            raise ValidationFailedError("compound components share an ordinal")
        seen.add(component.ordinal)
        if not component.child_is_active:
            raise ValidationFailedError(
                "compound unit references an inactive child; the definition cannot resolve"
            )
        if component.child_unit.id == parent.id:
            raise ValidationFailedError("compound unit cannot list itself as a component")
        if component.child_unit.company_id != parent.company_id:
            raise ValidationFailedError("compound components must stay in the same company")
        total *= Fraction(component.quantity)
    return total


def validate_measured_quantity(
    *,
    entered_unit: UnitDefinition,
    entered_quantity: DecimalInput,
    measured_unit: UnitDefinition,
    measured_quantity: DecimalInput,
) -> tuple[Decimal, Decimal]:
    """Validate both measurements; a nominal pack ratio never supplies actual weight."""
    if entered_unit.company_id != measured_unit.company_id:
        raise ValidationFailedError("measured units must belong to the same company")
    validate_measured_units(entered_unit.id, measured_unit.id)
    entered = entered_unit.quantity.validate(entered_quantity)
    measured = measured_unit.quantity.validate(measured_quantity)
    if entered <= 0 or measured <= 0:
        raise ValidationFailedError("both measured quantities must be positive")
    return entered, measured


def validate_measured_units(entered_unit_id: uuid.UUID, base_unit_id: uuid.UUID) -> None:
    if entered_unit_id == base_unit_id:
        raise ValidationFailedError("measured entry requires distinct entered and base units")


def validate_serial_rule(dimension: str, rule: QuantityRule) -> None:
    if dimension != "COUNT" or rule.decimal_places != 0:
        raise ValidationFailedError("serialized stock requires a whole-count base quantity rule")
