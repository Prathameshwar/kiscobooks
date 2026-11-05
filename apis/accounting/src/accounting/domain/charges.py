"""Reproducible overdue charges from dated principal movements."""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, DecimalException, localcontext
from itertools import pairwise

from billing_platform.constants import MONEY_MAX
from billing_platform.errors import ValidationFailedError
from billing_platform.money import MoneyError, RoundingMode, quantize_storage, round_for_display

from accounting.domain.ledger import exact_positive


@dataclass(frozen=True)
class Movement:
    date: dt.date
    reduction: Decimal


@dataclass(frozen=True)
class ChargeTerms:
    method: str
    rate: Decimal
    rate_period: str
    compound: str
    basis: str
    day_basis: int
    minimum: Decimal
    cap: Decimal | None


def total_charge(
    principal: Decimal,
    origin: dt.date,
    end: dt.date,
    movements: tuple[Movement, ...],
    terms: ChargeTerms,
    *,
    precision: int,
    rounding: RoundingMode,
) -> Decimal:
    exact_positive(principal)
    exact_positive(terms.rate)
    if (
        terms.method not in {"FIXED", "INTEREST"}
        or terms.rate_period not in {"ANNUAL", "MONTHLY", "DAILY"}
        or terms.compound not in {"SIMPLE", "DAILY"}
        or terms.basis not in {"OUTSTANDING", "ORIGINAL"}
        or terms.day_basis not in {360, 365}
    ):
        raise ValidationFailedError("invalid overdue charge calculation policy")
    if (
        terms.minimum < 0
        or not terms.minimum.is_finite()
        or (
            terms.cap is not None
            and (not terms.cap.is_finite() or terms.cap < terms.minimum or terms.cap > MONEY_MAX)
        )
    ):
        raise ValidationFailedError("invalid charge minimum or cap")
    days = (end - origin).days
    if not 0 <= days <= 3650 or len(movements) > 10000:
        raise ValidationFailedError(
            "charge calculation exceeds the supported date or movement range"
        )
    changes: dict[dt.date, Decimal] = {}
    for movement in movements:
        if not isinstance(movement.reduction, Decimal) or not movement.reduction.is_finite():
            raise ValidationFailedError("principal movements require exact finite decimals")
        if movement.date < end:
            date = max(origin, movement.date)
            changes[date] = changes.get(date, Decimal(0)) + movement.reduction
    boundaries = sorted({origin, end, *changes})
    amount = Decimal(0)
    outstanding = principal
    with localcontext() as context:
        context.prec = 48
        denominator = (
            terms.day_basis
            if terms.rate_period == "ANNUAL"
            else 30
            if terms.rate_period == "MONTHLY"
            else 1
        )
        daily = terms.rate / Decimal(100) / denominator
        try:
            for start, stop in pairwise(boundaries):
                outstanding -= changes.get(start, Decimal(0))
                if not 0 <= outstanding <= principal:
                    raise ValidationFailedError("principal movement history does not reconcile")
                if outstanding == 0:
                    continue
                basis = principal if terms.basis == "ORIGINAL" else outstanding
                if terms.method == "FIXED":
                    amount = terms.rate
                    break
                if terms.compound == "SIMPLE":
                    amount += basis * daily * (stop - start).days
                else:
                    # Each outstanding principal unit ages from the immutable accrual origin.
                    # This makes splitting a run into intervals give the same cumulative result.
                    amount += basis * (
                        (1 + daily) ** (stop - origin).days - (1 + daily) ** (start - origin).days
                    )
                if amount > MONEY_MAX:
                    raise ValidationFailedError("charge exceeds the supported monetary range")
            if amount > 0:
                amount = max(amount, terms.minimum)
                if terms.cap is not None:
                    amount = min(amount, terms.cap)
            return quantize_storage(round_for_display(amount, precision, rounding))
        except (DecimalException, MoneyError) as exc:
            raise ValidationFailedError("charge exceeds the supported monetary range") from exc
