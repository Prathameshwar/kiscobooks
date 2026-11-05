"""Credit limit and overdue rules independent of storage and transport."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from billing_platform.constants import MONEY_MAX
from billing_platform.errors import ValidationFailedError


@dataclass(frozen=True)
class Decision:
    status: Literal["ALLOW", "WARN", "BLOCK", "OVERRIDE_REQUIRED"]
    projected: Decimal
    reasons: tuple[str, ...]


def decide(
    exposure: Decimal,
    reserved: Decimal,
    proposed: Decimal,
    limit: Decimal | None,
    overdue: Decimal,
    tolerance: Decimal,
    enforcement: str,
    *,
    enabled: bool = True,
) -> Decision:
    for amount in (
        exposure,
        reserved,
        proposed,
        overdue,
        tolerance,
        *((limit,) if limit is not None else ()),
    ):
        if (
            not isinstance(amount, Decimal)
            or not amount.is_finite()
            or amount < 0
            or amount > MONEY_MAX
        ):
            raise ValidationFailedError("credit values must be bounded nonnegative exact decimals")
    if enforcement not in {"WARN", "BLOCK", "OVERRIDE"}:
        raise ValidationFailedError("invalid credit enforcement")
    projected = exposure + reserved + proposed
    if projected > MONEY_MAX:
        raise ValidationFailedError("credit exposure exceeds the supported range")
    reasons = (
        tuple(
            reason
            for condition, reason in (
                (limit is not None and projected > limit, "LIMIT_EXCEEDED"),
                (overdue > tolerance, "OVERDUE"),
            )
            if condition
        )
        if enabled
        else ()
    )
    status: Literal["ALLOW", "WARN", "BLOCK", "OVERRIDE_REQUIRED"] = "ALLOW"
    if reasons:
        status = (
            "WARN"
            if enforcement == "WARN"
            else "OVERRIDE_REQUIRED"
            if enforcement == "OVERRIDE"
            else "BLOCK"
        )
    return Decision(status, projected, reasons)
