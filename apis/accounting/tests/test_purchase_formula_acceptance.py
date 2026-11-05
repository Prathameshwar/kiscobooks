"""Native owner acceptance for the recipes selected in Purchase entry."""

from decimal import Decimal

import pytest

from accounting.domain.invoice_calculation import Component, Supply, Tax, calculate

D = Decimal


@pytest.mark.parametrize(
    "components,commercial,payable",
    [
        ((), "1000.00", "1180.00"),
        (
            (
                Component("trade", ("bill",), D(10)),
                Component("extra", ("bill",), D(5), dependencies=("trade",)),
            ),
            "855.00",
            "1008.90",
        ),
        (
            (Component("trade", ("bill",), D(10)), Component("extra", ("bill",), D(5))),
            "850.00",
            "1003.00",
        ),
        (
            (
                Component("trade", ("bill",), D(10)),
                Component("packing", ("bill",), D(2), effect="ADD", dependencies=("trade",)),
                Component(
                    "freight",
                    ("bill",),
                    D(100),
                    effect="ADD",
                    kind="FIXED",
                    dependencies=("trade",),
                ),
            ),
            "1018.00",
            "1201.24",
        ),
        ((Component("trade", ("bill",), D(10), basis="GROSS_INCL_TAX"),), "900.00", "1062.00"),
        (
            (
                Component("trade", ("bill",), D(10)),
                Component("extra", ("bill",), D(5), dependencies=("trade",)),
                Component("third", ("bill",), D(2), dependencies=("trade", "extra")),
            ),
            "837.90",
            "988.72",
        ),
    ],
)
def test_native_owner_recipe_amounts(components, commercial, payable):
    result = calculate((Supply("bill", D(1000), taxes=(Tax("igst", "IGST", D(18)),)),), components)
    assert result.commercial_total == D(commercial)
    assert result.payable == D(payable)


def test_selected_rows_preserve_each_rows_gst_rate_in_gross_adjustments():
    supplies = (
        Supply("a", D(1000), taxes=(Tax("a-tax", "IGST", D(18)),)),
        Supply("b", D(500), taxes=(Tax("b-tax", "IGST", D(5)),)),
    )
    result = calculate(supplies, (Component("trade", ("a", "b"), D(10), basis="GROSS_INCL_TAX"),))
    assert result.commercial_total == D("1350.00")
    assert result.payable == D("1534.50")


def test_named_basis_can_discount_prior_supplier_charges():
    result = calculate(
        (Supply("bill", D(100), taxes=(Tax("igst", "IGST", D(18)),)),),
        (
            Component("freight", ("bill",), D(100), kind="FIXED", effect="ADD"),
            Component("trade", ("bill",), D(75), dependencies=("freight",)),
        ),
    )
    assert result.commercial_total == D("50.00")
    assert result.payable == D("59.00")
