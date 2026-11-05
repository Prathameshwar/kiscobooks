"""Exact committed source-count and posted-journal control deltas; no persistence."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext


@dataclass(frozen=True)
class Contribution:
    present: bool
    currency: str | None = None
    debit: Decimal = Decimal(0)
    credit: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        if not self.debit.is_finite() or not self.credit.is_finite():
            raise ValueError("source control must be finite")
        with localcontext() as arithmetic:
            arithmetic.prec = 48
            if any(
                abs(value) >= Decimal("1000000000000000")
                or value != value.quantize(Decimal("0.0001"))
                for value in (self.debit, self.credit)
            ):
                raise ValueError("source contribution exceeds exact DECIMAL(19,4)")
        if self.currency is None:
            if self.debit or self.credit:
                raise ValueError("source control requires a currency")
        elif not self.present or self.debit <= 0 or self.debit != self.credit:
            raise ValueError("posted source control must be positive and balanced")


def advance(
    counts: Mapping[str, int],
    totals: Mapping[str, Mapping[str, str]],
    changes: Iterable[tuple[str, Contribution, Contribution]],
) -> tuple[dict[str, int], dict[str, dict[str, str]]]:
    sizes = dict(counts)
    values = {
        currency: {side: Decimal(value) for side, value in sides.items()}
        for currency, sides in totals.items()
    }
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for entity, before, after in changes:
            sizes[entity] += int(after.present) - int(before.present)
            if sizes[entity] < 0:
                raise ValueError("source control count became negative")
            for sign, contribution in ((-1, before), (1, after)):
                if contribution.currency is None:
                    continue
                bucket = values.setdefault(
                    contribution.currency, {"DEBIT": Decimal(0), "CREDIT": Decimal(0)}
                )
                bucket["DEBIT"] += sign * contribution.debit
                bucket["CREDIT"] += sign * contribution.credit
        for sides in values.values():
            if (
                set(sides) != {"DEBIT", "CREDIT"}
                or not all(value.is_finite() for value in sides.values())
                or sides["DEBIT"] < 0
                or sides["DEBIT"] != sides["CREDIT"]
            ):
                raise ValueError("source control became negative or unbalanced")
    return sizes, {
        currency: {side: format(value, ".4f") for side, value in sides.items()}
        for currency, sides in values.items()
        if any(sides.values())
    }
