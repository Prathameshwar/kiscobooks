from collections.abc import Callable
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.money import MoneyError

from catalog.domain.pricing import (
    RateGrid,
    Tier,
    percentage,
    positive,
    purchase_net,
    recipe_rate,
    select_tier,
    storage,
    validate_tiers,
)


def test_exact_rate_grids_and_recipes_preserve_basis() -> None:
    with localcontext() as ctx:
        ctx.prec = 4
        grid = RateGrid(2, Decimal("0.05"))
        assert grid.entered(Decimal("100.05")) == Decimal("100.0500")
        for mode, expected in (("UP", "106.70"), ("DOWN", "106.65"), ("HALF_UP", "106.65")):
            assert grid.rounded(
                recipe_rate(Fraction(80), "REFERENCE_COST_TARGET_MARGIN", Decimal(25)), mode
            ) == Decimal(expected)
        assert recipe_rate(Fraction(80), "REFERENCE_COST_PLUS_MARKUP", Decimal(25)) == 100
        assert recipe_rate(Fraction(100), "MRP_LESS_PERCENT", Decimal(10)) == 90
        assert grid.rounded(Fraction("1.025"), "HALF_UP") == Decimal("1.05")
        assert RateGrid(4).rounded(Fraction(1, 3000), "UP") == Decimal("0.0004")
    assert purchase_net(Decimal(80), "NONE", Decimal(0)) == 80
    assert purchase_net(Decimal(80), "PERCENT", Decimal(10)) == 72
    assert purchase_net(Decimal(80), "FIXED_PER_BASIS", Decimal(8)) == 72
    assert isinstance(storage(Fraction(1, 10000)), Decimal)
    assert RateGrid(4).entered(Decimal(0), free=True) == 0
    tiers = (Tier(Decimal(0), Decimal(10), Decimal(100)), Tier(Decimal(10), None, Decimal(90)))
    validate_tiers(tiers, RateGrid(2))
    assert select_tier(tiers, Decimal(10)) == 1
    assert select_tier(tiers, Decimal(9)) == 0


@pytest.mark.parametrize(
    "call",
    [
        lambda: positive(Decimal(0)),
        lambda: percentage(Decimal(-1)),
        lambda: percentage(Decimal(101)),
        lambda: percentage(Decimal(100), margin=True),
        lambda: storage(Fraction(1, 3)),
        lambda: RateGrid(5),
        lambda: RateGrid(2, Decimal(0)),
        lambda: RateGrid(2, Decimal("0.001")),
        lambda: RateGrid(2).entered(Decimal(-1)),
        lambda: RateGrid(2).entered(Decimal(0)),
        lambda: RateGrid(2).entered(Decimal("1.001")),
        lambda: RateGrid(2, Decimal("0.05")).entered(Decimal("1.02")),
        lambda: RateGrid(2).rounded(Fraction(-1), "UP"),
        lambda: RateGrid(2).rounded(Fraction(1), "UNKNOWN"),
        lambda: purchase_net(Decimal(80), "PERCENT", Decimal(101)),
        lambda: purchase_net(Decimal(80), "FIXED_PER_BASIS", Decimal(90)),
        lambda: purchase_net(Decimal(80), "NONE", Decimal(1)),
        lambda: purchase_net(Decimal("0.0001"), "PERCENT", Decimal(50)),
        lambda: recipe_rate(Fraction(-1), "MIN_MARKUP", Decimal(1)),
        lambda: recipe_rate(Fraction(1), "MIN_MARKUP", Decimal(-1)),
        lambda: recipe_rate(Fraction(80), "ALLOCATED_COST", Decimal(25)),
        lambda: select_tier((), Decimal(1)),
        lambda: select_tier((Tier(Decimal(0), None, Decimal(1)),) * 2, Decimal(1)),
    ],
)
def test_invalid_rates_fail_before_storage(call: Callable[[], object]) -> None:
    with pytest.raises((ValidationFailedError, MoneyError)):
        call()


@pytest.mark.parametrize(
    "tiers",
    [
        (),
        (Tier(Decimal(1), None, Decimal(1)),),
        (Tier(Decimal(0), Decimal(1), Decimal(1)),),
        (Tier(Decimal(0), None, Decimal(1)), Tier(Decimal(1), None, Decimal(1))),
        (Tier(Decimal(0), Decimal(0), Decimal(1)),),
        (Tier(Decimal(0), Decimal(2), Decimal(1)), Tier(Decimal(1), None, Decimal(1))),
        (Tier(Decimal(0), None, Decimal(1)),) * 65,
    ],
)
def test_tiers_reject_gaps_overlaps_and_uncovered_tails(tiers: tuple[Tier, ...]) -> None:
    with pytest.raises(ValidationFailedError):
        validate_tiers(tiers, RateGrid(2))
