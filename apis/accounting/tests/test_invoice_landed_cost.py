"""Landed cost is pure exact arithmetic (no database): owner decision 2026-11-03."""

from dataclasses import dataclass
from decimal import Decimal

import pytest

from accounting.domain.invoice_landed_cost import landed_cost


@dataclass(frozen=True)
class Tax:
    amount: Decimal
    supplier_charged: bool


TAXES = (Tax(Decimal("49.5000"), True), Tax(Decimal("49.5000"), True))


def test_claimable_gst_is_recoverable_tax_never_stock():
    assert landed_cost(Decimal("550.0000"), TAXES, claimable=True) == Decimal("550")


def test_non_claimable_gst_is_capitalised_exactly():
    cost = landed_cost(Decimal("550.0000"), TAXES, claimable=False)
    assert cost == Decimal("649") and isinstance(cost, Decimal)


def test_tax_the_supplier_did_not_charge_is_not_part_of_the_price_paid():
    assert landed_cost(Decimal("100"), (Tax(Decimal("18"), False),), claimable=False) == 100


@pytest.mark.parametrize("bad", [Decimal("-1"), 1.5, 100])
def test_only_a_non_negative_exact_decimal_is_costed(bad):
    with pytest.raises(ValueError):
        landed_cost(bad, (), claimable=True)
