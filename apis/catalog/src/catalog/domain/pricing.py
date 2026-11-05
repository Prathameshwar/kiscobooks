"""Exact commercial rates, tiers and bounded recipes; no basket or tax evaluator."""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from billing_platform.errors import ValidationFailedError
from billing_platform.exact import exact_decimal


def positive(value: Decimal) -> Decimal:
    value = exact_decimal(value)
    if value <= 0:
        raise ValidationFailedError("value must be positive")
    return value


def percentage(value: Decimal, *, margin: bool = False) -> Decimal:
    value = exact_decimal(value)
    if value < 0 or (value >= 100 if margin else value > 100):
        raise ValidationFailedError("percentage is outside its permitted range")
    return value


def storage(value: Fraction) -> Decimal:
    scaled = value * 10000
    if scaled.denominator != 1:
        raise ValidationFailedError(
            "result is not exactly representable; change the declared basis"
        )
    integer = scaled.numerator
    return exact_decimal(Decimal((int(integer < 0), tuple(map(int, str(abs(integer)))), -4)))


@dataclass(frozen=True)
class RateGrid:
    decimal_places: int
    increment: Decimal | None = None

    def __post_init__(self) -> None:
        exact_decimal(0, decimal_places=self.decimal_places)
        if self.increment is not None:
            positive(exact_decimal(self.increment, decimal_places=self.decimal_places))

    def entered(self, value: Decimal, *, free: bool = False) -> Decimal:
        amount = exact_decimal(value, decimal_places=self.decimal_places, increment=self.increment)
        if amount < 0 or (amount == 0 and not free):
            raise ValidationFailedError("zero prices require explicit effective free-sale policy")
        return amount

    def rounded(self, value: Fraction, mode: str) -> Decimal:
        if value < 0 or mode not in {"UP", "DOWN", "HALF_UP"}:
            raise ValidationFailedError("unsupported computed rate or rounding stage")
        step = Fraction(self.increment or Decimal(1).scaleb(-self.decimal_places))
        units = value / step
        floor, remainder = divmod(units.numerator, units.denominator)
        if (mode == "UP" and remainder) or (
            mode == "HALF_UP" and 2 * remainder >= units.denominator
        ):
            floor += 1
        return storage(floor * step)


@dataclass(frozen=True)
class Tier:
    minimum: Decimal
    maximum: Decimal | None
    amount: Decimal


def validate_tiers(tiers: tuple[Tier, ...], grid: RateGrid, *, free: bool = False) -> None:
    if not 1 <= len(tiers) <= 64:
        raise ValidationFailedError("volume pricing requires one to 64 tiers")
    expected = Decimal(0)
    for index, tier in enumerate(tiers):
        if exact_decimal(tier.minimum) != expected:
            raise ValidationFailedError("tiers must be ordered, contiguous and begin at zero")
        grid.entered(tier.amount, free=free)
        if tier.maximum is None:
            if index != len(tiers) - 1:
                raise ValidationFailedError("only the final tier may be unbounded")
        elif exact_decimal(tier.maximum) <= tier.minimum:
            raise ValidationFailedError("tier end must exceed its start")
        expected = tier.maximum if tier.maximum is not None else expected
    if tiers[-1].maximum is not None:
        raise ValidationFailedError("the final tier must cover all remaining quantities")


def select_tier(tiers: tuple[Tier, ...], quantity: Decimal) -> int:
    positive(quantity)
    matches = [
        i
        for i, row in enumerate(tiers)
        if row.minimum <= quantity and (row.maximum is None or quantity < row.maximum)
    ]
    if len(matches) != 1:
        raise ValidationFailedError("quantity has missing or ambiguous volume-price coverage")
    return matches[0]


def purchase_net(gross: Decimal, kind: str, discount: Decimal) -> Decimal:
    positive(gross)
    exact_decimal(discount)
    if kind == "NONE" and discount == 0:
        return gross
    if kind == "PERCENT":
        return storage(Fraction(gross) * (1 - Fraction(percentage(discount)) / 100))
    if kind == "FIXED_PER_BASIS" and 0 <= discount <= gross:
        return storage(Fraction(gross) - Fraction(discount))
    raise ValidationFailedError("purchase discount is incompatible with the gross quote")


def recipe_rate(source: Fraction, recipe: str, percent: Decimal) -> Fraction:
    exact_decimal(percent)
    if source < 0 or percent < 0:
        raise ValidationFailedError("recipe requires nonnegative source and percentage")
    if recipe == "MRP_LESS_PERCENT":
        return source * (1 - Fraction(percentage(percent)) / 100)
    if recipe in {"REFERENCE_COST_TARGET_MARGIN", "MIN_MARGIN"}:
        return source / (1 - Fraction(percentage(percent, margin=True)) / 100)
    if recipe in {"REFERENCE_COST_PLUS_MARKUP", "MIN_MARKUP"}:
        return source * (1 + Fraction(percent) / 100)
    raise ValidationFailedError("recipe requires an unavailable authoritative source")
