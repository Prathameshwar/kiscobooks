"""Typed future-product defaults; no layout, custom fields or physical stock execution."""

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from fractions import Fraction
from math import lcm

from billing_platform.errors import ValidationFailedError
from billing_platform.exact import exact_decimal

from catalog.domain.units import QuantityRule

DIMENSIONS = frozenset({"COUNT", "MASS", "VOLUME", "LENGTH", "AREA", "TIME", "JOB"})


@dataclass(frozen=True, slots=True)
class OptionSetting:
    mode: str = "INHERIT"
    default_enabled: bool | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"INHERIT", "DISABLED", "OPTIONAL", "REQUIRED"}:
            raise ValidationFailedError("unsupported native option requirement")
        if self.mode == "OPTIONAL":
            if type(self.default_enabled) is not bool:
                raise ValidationFailedError(
                    "optional selection requires an explicit boolean default"
                )
        elif self.default_enabled is not None:
            raise ValidationFailedError("only optional selection accepts a default choice")

    @property
    def enabled(self) -> bool:
        if self.mode == "INHERIT":
            raise ValidationFailedError("an inherited option needs a resolved source")
        return self.mode == "REQUIRED" or (self.mode == "OPTIONAL" and self.default_enabled is True)


def resolve_option(layers: tuple[OptionSetting, ...], *, baseline: OptionSetting) -> OptionSetting:
    """Layers are company/type/ancestor-to-nearest group; all hard restrictions survive."""
    if baseline.mode == "INHERIT" or len(layers) > 36:
        raise ValidationFailedError(
            "configuration option resolution needs a bounded concrete baseline"
        )
    applicable = (baseline, *(row for row in layers if row.mode != "INHERIT"))
    modes = {row.mode for row in applicable}
    if {"DISABLED", "REQUIRED"} <= modes:
        raise ValidationFailedError(
            "configuration contains contradictory required and disabled options"
        )
    if "REQUIRED" in modes:
        return OptionSetting("REQUIRED")
    if "DISABLED" in modes:
        return OptionSetting("DISABLED")
    return applicable[-1]


def require_capability(
    option: OptionSetting, *, feature_enabled: bool, required_by_type: bool
) -> None:
    if required_by_type and option.mode == "DISABLED":
        raise ValidationFailedError("configuration cannot disable a product-type requirement")
    if not feature_enabled and (option.mode == "REQUIRED" or option.enabled or required_by_type):
        raise ValidationFailedError("configuration requires an unavailable company capability")


@dataclass(frozen=True, slots=True)
class NumericDefault:
    dimension: str
    quantity: QuantityRule | None = None
    price_decimal_places: int | None = None
    price_increment: Decimal | None = None
    currency: str | None = None
    price_basis_quantity: Decimal | None = None

    def __post_init__(self) -> None:
        if self.dimension not in DIMENSIONS:
            raise ValidationFailedError("unsupported numeric-default dimension")
        if self.price_decimal_places is None:
            if self.price_increment is not None or self.currency is not None:
                raise ValidationFailedError(
                    "price-entry defaults require precision and currency together"
                )
        else:
            if (
                self.currency is None
                or len(self.currency) != 3
                or not self.currency.isascii()
                or not self.currency.isupper()
                or not self.currency.isalpha()
            ):
                raise ValidationFailedError("price-entry defaults require a currency code")
            exact_decimal("0", decimal_places=self.price_decimal_places)
            if self.price_increment is not None:
                step = exact_decimal(self.price_increment, decimal_places=self.price_decimal_places)
                if step <= 0:
                    raise ValidationFailedError("price increment must be positive")
                object.__setattr__(self, "price_increment", step)
        if self.price_basis_quantity is not None:
            basis = exact_decimal(self.price_basis_quantity)
            if basis <= 0:
                raise ValidationFailedError("price basis quantity must be positive")
            object.__setattr__(self, "price_basis_quantity", basis)


def narrow_quantity_default(default: QuantityRule | None, unit: QuantityRule) -> QuantityRule:
    """Narrow defaults to the unit; validate explicit overrides separately."""
    if default is None:
        return unit
    places = min(default.decimal_places, unit.decimal_places)
    # All three steps must hold: the default grid, unit grid and selected decimal scale.
    factors = [Fraction(row.increment) * 10_000 for row in (default, unit)]
    step = lcm(*(value.numerator for value in factors), 10 ** (4 - places))
    with localcontext(Context(prec=38)):
        increment = Decimal(step) / 10_000
    return QuantityRule(places, increment)
