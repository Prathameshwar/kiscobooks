"""Bounded native component validation, independent of invoice determination."""

from collections import Counter
from collections.abc import Sequence
from decimal import Decimal
from fractions import Fraction
from typing import Any, Literal, Protocol

from billing_platform.errors import ValidationFailedError

CONTEXTS = {"INTRA_STATE": {"CGST", "SGST"}, "INTRA_UT": {"CGST", "UTGST"}, "INTER_STATE": {"IGST"}}
GST_CEILINGS = {"CGST": Decimal(20), "SGST": Decimal(20), "UTGST": Decimal(20), "IGST": Decimal(40)}


class Component(Protocol):
    component_key: str
    component: Literal["CGST", "SGST", "UTGST", "IGST", "CESS"]
    kind: Literal["PERCENT", "FIXED_PER_UNIT"]
    percentage: Decimal | None
    position: int

    @property
    def rounding_mode(self) -> str: ...


def validate_components(
    applicability: str, treatment: str, components: Sequence[Component]
) -> None:
    if applicability not in CONTEXTS or treatment not in {"TAXABLE", "NIL_RATED"}:
        raise ValidationFailedError(
            "rate components require a supported taxable or nil-rated context"
        )
    if not 1 <= len(components) <= 16:
        raise ValidationFailedError("a rate must have one to sixteen components")
    if len({row.component_key for row in components}) != len(components) or len(
        {row.position for row in components}
    ) != len(components):
        raise ValidationFailedError("component keys and positions must be distinct")
    taxes = [row for row in components if row.component != "CESS"]
    if Counter(row.component for row in taxes) != Counter(CONTEXTS[applicability]):
        raise ValidationFailedError("components do not match the declared supply context")
    if any(row.kind != "PERCENT" or row.percentage is None for row in taxes):
        raise ValidationFailedError("GST components require explicit percentages")
    if any(
        row.percentage is not None
        and (
            not row.percentage.is_finite() or not 0 <= row.percentage <= GST_CEILINGS[row.component]
        )
        for row in taxes
    ):
        raise ValidationFailedError("GST component exceeds its statutory percentage ceiling")
    if len(taxes) == 2 and taxes[0].percentage != taxes[1].percentage:
        raise ValidationFailedError("central and state/UT GST percentages must be equal")
    if len({row.rounding_mode for row in taxes}) > 1:
        raise ValidationFailedError("central and state/UT GST components must share rounding")
    if treatment == "NIL_RATED":
        if len(taxes) != len(components) or any(row.percentage != 0 for row in taxes):
            raise ValidationFailedError(
                "nil-rated definitions require explicit zero GST and no cess"
            )
    elif not any(row.percentage and row.percentage > 0 for row in taxes):
        raise ValidationFailedError("taxable definitions require a positive GST component")


def signature(components: Sequence[Any]) -> tuple[Fraction, str, tuple[Any, ...]]:
    """GST total, GST rounding and explicitly supported compensation-cess components.

    Component labels and display positions do not change tax. GST rounding is part of the
    signature so an intra-state and an inter-state rate cannot round the same supply
    differently. Per-unit rates are compared exactly, including their unit/currency/rounding.
    """
    gst = sum(
        (Fraction(row.percentage) for row in components if row.component != "CESS"), Fraction()
    )
    rounding = "|".join(
        sorted({row.rounding_mode for row in components if row.component != "CESS"})
    )
    cess = []
    for row in components:
        if row.component != "CESS":
            continue
        if row.kind == "PERCENT":
            cess.append(("PERCENT", "", "", Fraction(row.percentage), row.rounding_mode))
        else:
            cess.append(
                (
                    "FIXED_PER_UNIT",
                    str(row.unit_id),
                    row.currency,
                    Fraction(row.amount) / Fraction(row.basis_quantity),
                    row.rounding_mode,
                )
            )
    return gst, rounding, tuple(sorted(cess))


def classification_matches(code_system: str, code: str, applicability: Any) -> bool:
    return code_system == applicability.code_system and (
        code == applicability.code
        if applicability.match_kind == "EXACT"
        else code.startswith(applicability.code)
    )
