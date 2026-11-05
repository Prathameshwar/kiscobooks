"""Exact, non-posting quantities for a bounded manufacturing BOM preview.

These calculations are definition evidence only. Accounting owns physical movements,
custody, WIP and actual cost; a preview must never be treated as an owner receipt.
"""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Literal
from uuid import UUID

from billing_platform.errors import ValidationFailedError
from billing_platform.exact import exact_decimal, exact_rate
from billing_platform.money import MoneyError


@dataclass(frozen=True, slots=True)
class Component:
    line_key: UUID
    item_id: UUID
    quantity: Decimal
    basis: Literal["GROSS_INPUT", "NET_REQUIRED"] = "GROSS_INPUT"
    loss_fraction: Decimal = Decimal(0)
    timing: Literal["PER_BASIS", "PER_RUN"] = "PER_BASIS"


@dataclass(frozen=True, slots=True)
class Output:
    line_key: UUID
    item_id: UUID
    nominal_quantity: Decimal
    yield_fraction: Decimal = Decimal(1)
    role: Literal["PRIMARY", "CO_PRODUCT", "BY_PRODUCT", "SCRAP"] = "PRIMARY"


@dataclass(frozen=True, slots=True)
class Requirement:
    line_key: UUID
    item_id: UUID
    required_quantity: Decimal


@dataclass(frozen=True, slots=True)
class ExpectedOutput:
    line_key: UUID
    item_id: UUID
    role: str
    expected_quantity: Decimal


@dataclass(frozen=True, slots=True)
class Preview:
    nominal_run_quantity: Decimal
    requirements: tuple[Requirement, ...]
    outputs: tuple[ExpectedOutput, ...]


def _positive(value: Decimal, label: str) -> Decimal:
    try:
        result = exact_decimal(value)
    except MoneyError as exc:
        raise ValidationFailedError(f"{label} must be exactly representable") from exc
    if result <= 0:
        raise ValidationFailedError(f"{label} must be positive")
    return result


def _fraction(value: Decimal, label: str, *, allow_zero: bool = False) -> Fraction:
    try:
        result = exact_rate(value)
    except MoneyError as exc:
        raise ValidationFailedError(f"{label} must be an exact eight-place rate") from exc
    if result < 0 or (not allow_zero and result == 0) or result > 1:
        raise ValidationFailedError(f"{label} must be within its supported fraction range")
    return Fraction(result)


def _storage(value: Fraction, label: str) -> Decimal:
    scaled = value * 10_000
    if scaled.denominator != 1:
        raise ValidationFailedError(f"{label} is not representable at four quantity places")
    result = Decimal(scaled.numerator).scaleb(-4)
    try:
        return exact_decimal(result)
    except MoneyError as exc:
        raise ValidationFailedError(f"{label} exceeds quantity storage") from exc


def preview(
    requested_good_quantity: Decimal,
    components: tuple[Component, ...],
    outputs: tuple[Output, ...],
    *,
    run_count: int | None = None,
) -> Preview:
    """Scale one published-basis recipe without rounding or collapsing line identity."""
    requested = _positive(requested_good_quantity, "requested output")
    if not outputs or len(outputs) > 100 or len(components) > 1000:
        raise ValidationFailedError("BOM preview exceeds supported output or component count")
    line_keys = [component.line_key for component in components] + [
        output.line_key for output in outputs
    ]
    if len(set(line_keys)) != len(line_keys):
        raise ValidationFailedError("BOM line keys must be unique")
    primaries = [row for row in outputs if row.role == "PRIMARY"]
    if len(primaries) != 1:
        raise ValidationFailedError("manufacturing BOM requires one primary output")
    if any(row.role not in {"PRIMARY", "CO_PRODUCT", "BY_PRODUCT", "SCRAP"} for row in outputs):
        raise ValidationFailedError("unsupported BOM output role")
    output_items = {row.item_id for row in outputs}
    if len(output_items) != len(outputs) or output_items & {row.item_id for row in components}:
        raise ValidationFailedError("output items must be distinct from each other and inputs")
    if any(
        row.basis not in {"GROSS_INPUT", "NET_REQUIRED"}
        or row.timing not in {"PER_BASIS", "PER_RUN"}
        for row in components
    ):
        raise ValidationFailedError("unsupported BOM component basis or timing")
    if run_count is not None and (type(run_count) is not int or not 1 <= run_count <= 1000):
        raise ValidationFailedError("run count must be a positive bounded integer")
    if any(row.timing == "PER_RUN" for row in components) and run_count is None:
        raise ValidationFailedError("fixed-per-run inputs require an explicit run count")

    primary = primaries[0]
    basis = _positive(primary.nominal_quantity, "primary output basis")
    primary_yield = _fraction(primary.yield_fraction, "primary yield")
    scaling = Fraction(requested) / (Fraction(basis) * primary_yield)
    nominal = _storage(Fraction(basis) * scaling, "nominal run output")

    expected: list[ExpectedOutput] = []
    for row in outputs:
        nominal_output = _positive(row.nominal_quantity, "nominal output")
        output_yield = _fraction(row.yield_fraction, "output yield")
        good = _storage(Fraction(nominal_output) * output_yield * scaling, "expected output")
        expected.append(ExpectedOutput(row.line_key, row.item_id, row.role, good))
    if expected[outputs.index(primary)].expected_quantity != requested:
        raise ValidationFailedError("primary output does not equal the requested good quantity")

    required: list[Requirement] = []
    for component in components:
        quantity = _positive(component.quantity, "component quantity")
        loss = _fraction(component.loss_fraction, "component loss", allow_zero=True)
        if loss >= 1:
            raise ValidationFailedError("component loss cannot consume the entire input")
        if component.timing == "PER_RUN":
            if run_count is None:
                raise ValidationFailedError("fixed-per-run inputs require an explicit run count")
            multiplier = Fraction(run_count)
        else:
            multiplier = scaling
        amount = Fraction(quantity) * multiplier
        if component.basis == "NET_REQUIRED":
            amount /= 1 - loss
        elif loss:
            raise ValidationFailedError("gross input cannot also be grossed up for loss")
        required.append(
            Requirement(
                component.line_key, component.item_id, _storage(amount, "component requirement")
            )
        )
    return Preview(nominal, tuple(required), tuple(expected))
