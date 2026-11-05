"""Commercial acceptance examples and rejection of ambiguous arithmetic inputs."""

from dataclasses import replace
from decimal import Decimal as D  # noqa: N817 - compact monetary fixtures
from fractions import Fraction

import pytest
from billing_platform.errors import ValidationFailedError

from accounting.domain.invoice_calculation import (
    Component,
    Quantity,
    Supply,
    Tax,
    apportion,
    calculate,
    exact,
    money,
)


def test_published_component_rounding_is_independent_of_company_rounding():
    result = calculate(
        (
            Supply(
                "service",
                D("1.01"),
                taxes=(
                    Tax("c", "CGST", D(9), rounding_mode="UP"),
                    Tax("s", "SGST", D(9), rounding_mode="UP"),
                ),
            ),
        ),
        rounding_mode="DOWN",
    )
    assert [row.amount for row in result.lines[0].taxes] == [D("0.10"), D("0.10")]
    assert result.payable == D("1.21")
    with pytest.raises(ValidationFailedError, match="rounding"):
        calculate((Supply("service", D(1), taxes=(Tax("c", "CGST", D(9), rounding_mode="bad"),)),))


def gst(rate: str) -> tuple[Tax, ...]:
    return (Tax("central", "CGST", D(rate)), Tax("state", "SGST", D(rate)))


def piece(key: str, amount: str, billed: str, rate: str = "9") -> Supply:
    return Supply(
        key, D(amount), quantities=(Quantity("BILLED", D(billed), "PCS"),), taxes=gst(rate)
    )


def test_stacked_purchase_acceptance_and_display_order_independence() -> None:
    lines = (piece("a", "1000", "10"), piece("b", "500", "5", "2.5"))
    components = (
        Component("a_trade", ("a",), D(10)),
        Component("a_extra", ("a",), D(10), dependencies=("a_trade",)),
        Component(
            "a_quantity",
            ("a",),
            D(1),
            kind="PER_QUANTITY",
            allocation="QUANTITY",
            quantity_basis="BILLED",
            unit="PCS",
        ),
        Component("b_fixed", ("b",), D(100), kind="FIXED"),
        Component(
            "invoice_discount",
            ("a", "b"),
            D(10),
            dependencies=("a_trade", "a_extra", "a_quantity", "b_fixed"),
        ),
        Component(
            "a_packing",
            ("a",),
            D(2),
            effect="ADD",
            kind="PER_QUANTITY",
            allocation="QUANTITY",
            quantity_basis="BILLED",
            unit="PCS",
        ),
        Component("b_handling", ("b",), D(10), effect="ADD", kind="FIXED"),
        Component(
            "freight",
            ("a", "b"),
            D(111),
            effect="ADD",
            kind="FIXED",
            dependencies=(
                "a_trade",
                "a_extra",
                "a_quantity",
                "b_fixed",
                "invoice_discount",
                "a_packing",
                "b_handling",
            ),
        ),
    )
    result = calculate(lines, components)
    assert result == calculate(tuple(reversed(lines)), tuple(reversed(components)))
    assert [line.taxable for line in result.lines] == [D("814"), D("407")]
    assert [line.payable for line in result.lines] == [D("960.52"), D("427.36")]
    assert result.payable == D("1387.88")
    assert result.tax_total == D("166.88")


def test_sequential_common_bases_and_selected_charge_basis() -> None:
    line = (Supply("service", D(1000)),)
    trade = Component("trade", ("service",), D(10))
    later = Component("later", ("service",), D(5))
    assert calculate(line, (trade, later)).payable == D(850)
    assert calculate(line, (trade, replace(later, dependencies=("trade",)))).payable == D(855)
    charge = Component("charge", ("service",), D(100), effect="ADD", kind="FIXED")
    assert calculate(line, (charge, replace(trade, dependencies=("charge",)))).payable == D(990)


def test_commercial_tax_and_cost_allocations_are_independent() -> None:
    lines = (piece("a", "1000", "10"), piece("b", "500", "5"))
    freight = Component(
        "freight",
        ("a", "b"),
        D(90),
        effect="ADD",
        kind="FIXED",
        commercial=False,
        cost_targets=("b",),
    )
    result = calculate(lines, (freight,))
    assert result.commercial_total == D(1500)
    assert result.tax_total == D("286.20")
    assert [(a.line_key, a.amount) for a in result.allocations if a.purpose == "STOCK_COST"] == [
        ("b", D(90))
    ]
    assert not any(a.purpose == "COMMERCIAL" for a in result.allocations)


def test_inclusive_mixed_rate_fixed_gross_discount_and_rounding() -> None:
    lines = (
        replace(piece("a", "118", "1"), inclusive=True),
        replace(piece("b", "105", "1", "2.5"), inclusive=True),
    )
    discount = Component("discount", ("a", "b"), D("22.30"), kind="FIXED", basis="GROSS_INCL_TAX")
    result = calculate(lines, (discount,), invoice_increment=D(1))
    assert result.commercial_total == D(180)
    assert result.tax_total == D("20.70")
    assert result.rounding == D("0.30")
    assert result.payable == D(201)


def test_percentage_discount_on_inclusive_item_uses_entered_gross_with_fixed_cess() -> None:
    line = Supply(
        "item", D("128.00"), inclusive=True,
        quantities=(Quantity("BILLED", D(1), "PCS"),),
        taxes=(
            *gst("9"),
            Tax("cess", "CESS", D(10), basis="QUANTITY", quantity_basis="BILLED", unit="PCS"),
        ),
    )
    discount = Component("discount", ("item",), D(10), basis="GROSS_INCL_TAX")
    result = calculate((line,), (discount,))
    assert result.lines[0].entered == D("100.00")
    assert result.components[0].basis_amount == D("128.00")
    assert result.components[0].input_amount == D("-12.80")
    assert result.payable == D("115.20")
    surcharge = Component(
        "surcharge", ("item",), D(10), effect="ADD", basis="GROSS_INCL_TAX"
    )
    charged = calculate((line,), (surcharge,))
    assert charged.components[0].input_amount == D("12.80")
    assert charged.payable == D("140.80")


def test_invoice_gross_discount_handles_inclusive_and_exclusive_items() -> None:
    inclusive = Supply(
        "inclusive", D("128.00"), inclusive=True,
        quantities=(Quantity("BILLED", D(1), "PCS"),),
        taxes=(
            *gst("9"),
            Tax("cess", "CESS", D(10), basis="QUANTITY", quantity_basis="BILLED", unit="PCS"),
        ),
    )
    exclusive = piece("exclusive", "100.00", "1")
    discount = Component(
        "bill_discount", ("inclusive", "exclusive"), D(10),
        basis="GROSS_INCL_TAX",
    )
    result = calculate((inclusive, exclusive), (discount,))
    assert result.components[0].basis_amount == D("246.00")
    assert result.components[0].input_amount == D("-24.60")
    assert result.payable == D("221.40")


def test_inclusive_price_rejects_tax_only_payable_by_recipient() -> None:
    line = Supply(
        "purchase", D("118.00"), inclusive=True,
        taxes=(Tax("rcm", "IGST", D(18), supplier_charged=False),),
    )
    with pytest.raises(ValidationFailedError, match="supplier-charged"):
        calculate((line,))


def test_distinct_tax_targets_and_weights_conserve_each_purpose() -> None:
    lines = (piece("a", "1000", "1"), piece("b", "500", "5", "2.5"))
    charge = Component(
        "freight",
        ("a", "b"),
        D(60),
        effect="ADD",
        kind="FIXED",
        tax_allocation="QUANTITY",
        quantity_basis="BILLED",
        unit="PCS",
        cost_targets=("b",),
    )
    result = calculate(lines, (charge,))
    shares = {(a.purpose, a.line_key): a.amount for a in result.allocations}
    assert shares == {
        ("COMMERCIAL", "a"): D(40),
        ("COMMERCIAL", "b"): D(20),
        ("TAX_BASE", "a"): D(10),
        ("TAX_BASE", "b"): D(50),
        ("STOCK_COST", "b"): D(60),
    }
    assert result.payable == D("1769.30")
    selected = calculate(lines, (replace(charge, tax_targets=("b",)),))
    assert [a.amount for a in selected.allocations if a.purpose == "TAX_BASE"] == [D(60)]
    assert selected.payable == D(1768)
    assert selected == calculate(tuple(reversed(lines)), (replace(charge, tax_targets=("b",)),))


def test_separate_tax_allocation_preserves_named_dependency_basis() -> None:
    lines = (piece("a", "100", "1"), piece("b", "100", "1"))
    first = Component("first", ("a",), D(50), kind="FIXED")
    next_ = Component(
        "next",
        ("a", "b"),
        D(30),
        kind="FIXED",
        dependencies=("first",),
        tax_targets=("a", "b"),
        tax_allocation="VALUE",
    )
    result = calculate(lines, (next_, first))
    assert [
        (a.line_key, a.amount)
        for a in result.allocations
        if a.component_key == "next" and a.purpose == "TAX_BASE"
    ] == [
        ("a", D(-10)),
        ("b", D(-20)),
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {"tax_targets": ("missing",)},
        {"tax_targets": ("a", "a")},
        {"tax_targets": ("a",), "taxable": False},
        {"tax_targets": ("a",), "basis": "GROSS_INCL_TAX"},
        {"tax_allocation": "UNKNOWN"},
        {"tax_allocation": "QUANTITY"},
        {"tax_targets": ("b",)},
    ],
)
def test_invalid_separate_tax_distributions_are_rejected(changes) -> None:
    # The final case exceeds b's taxable balance despite sufficient commercial value.
    with pytest.raises(ValidationFailedError):
        calculate(
            (piece("a", "100", "1"), piece("b", "10", "1")),
            (replace(Component("d", ("a",), D(50), kind="FIXED"), **changes),),
        )


def test_quantity_tax_and_reverse_charge_do_not_inflate_supplier_payable() -> None:
    line = piece("a", "100", "10")
    line = replace(
        line,
        taxes=(
            Tax(
                "cess",
                "CESS",
                D(2),
                basis="QUANTITY",
                quantity_basis="BILLED",
                unit="PCS",
                denominator=D(100),
            ),
            Tax("integrated", "IGST", D(18), supplier_charged=False),
        ),
    )
    result = calculate((line,))
    assert result.tax_total == D("18.20")
    assert result.charged_tax_total == D("0.20")
    assert result.payable == D("100.20")
    assert calculate((replace(line, amount=D("100.20"), inclusive=True),)).payable == D("100.20")


def test_actual_billed_and_measured_denominators_are_explicit() -> None:
    line = replace(
        piece("a", "1000", "10"),
        quantities=(
            Quantity("BILLED", D(10), "PCS"),
            Quantity("ACTUAL", D(11), "PCS"),
            Quantity("MEASURED", D(250), "KG"),
        ),
    )
    charge = Component(
        "packing",
        ("a",),
        D(2),
        effect="ADD",
        kind="PER_QUANTITY",
        allocation="QUANTITY",
        quantity_basis="ACTUAL",
        unit="PCS",
    )
    freight = replace(
        charge, key="freight", value=D(50), quantity_basis="MEASURED", unit="KG", denominator=D(100)
    )
    result = calculate((line,), (charge, freight))
    assert {row.key: row.amount for row in result.components} == {
        "packing": D(22),
        "freight": D(125),
    }
    with pytest.raises(ValidationFailedError, match="unit evidence"):
        calculate((line,), (replace(freight, unit="PCS"),))


def test_allocation_residual_is_stable_and_reconciles() -> None:
    weights = (("c", Fraction(1)), ("b", Fraction(1)), ("a", Fraction(1)))
    assert apportion(D("0.02"), weights, 2) == {"a": D("0.01"), "b": D("0.01"), "c": D(0)}
    assert apportion(D("-0.02"), weights, 2) == {"a": D("-0.01"), "b": D("-0.01"), "c": D(0)}
    assert sum(apportion(D("100000000000000.01"), weights, 2).values()) == D("100000000000000.01")


@pytest.mark.parametrize(
    "mode,expected", [("UP", "1.01"), ("DOWN", "1"), ("HALF_UP", "1.01"), ("HALF_EVEN", "1")]
)
def test_rounding_is_explicit_and_symmetric(mode: str, expected: str) -> None:
    assert money(Fraction(201, 200), 2, mode) == D(expected)
    assert money(-Fraction(201, 200), 2, mode) == -D(expected)


@pytest.mark.parametrize(
    "component",
    [
        Component("a", ("missing",), D(1)),
        Component("a", ("s", "s"), D(1)),
        Component("a", ("s",), D(1), dependencies=("missing",)),
        Component("a", ("s",), D(1), dependencies=("a",)),
        Component("a", ("s",), D(1), cost_targets=("missing",)),
        Component("a", ("s",), D(-1)),
        Component("a", ("s",), D(101)),
        Component("a", ("s",), D(101), kind="FIXED"),
        Component("a", ("s",), D(1), kind="FORMULA"),
        Component("a", ("s",), D(1), basis="UNKNOWN"),
        Component("a", ("s",), D(1), effect="NEGATIVE"),
        Component("a", ("s",), D(1), allocation="UNKNOWN"),
        Component("a", ("s",), D(1), commercial=False, taxable=False),
        Component("a", ("s",), D(1), kind="PER_QUANTITY", denominator=D(0)),
        Component("a", ("s",), D(1), denominator=D(2)),
    ],
)
def test_ambiguous_or_excessive_components_are_refused(component: Component) -> None:
    with pytest.raises(ValidationFailedError):
        calculate((Supply("s", D(100)),), (component,))


def test_cycles_and_fanout_are_bounded() -> None:
    line = Supply("s", D(100))
    with pytest.raises(ValidationFailedError, match="cycle"):
        calculate(
            (line,),
            (
                Component("a", ("s",), D(1), dependencies=("b",)),
                Component("b", ("s",), D(1), dependencies=("a",)),
            ),
        )
    lines = tuple(Supply(str(i), D(100)) for i in range(200))
    components = tuple(Component(f"c{i}", tuple(row.key for row in lines), D(1)) for i in range(11))
    with pytest.raises(ValidationFailedError, match="allocation limit"):
        calculate(lines, components)


@pytest.mark.parametrize("value", [D("NaN"), D("Infinity"), D("0.00001"), D("1000000000000000")])
def test_storage_limits(value: D) -> None:
    with pytest.raises(ValidationFailedError):
        exact(value)


def test_rate_storage_limit_is_19_8() -> None:
    with pytest.raises(ValidationFailedError):
        exact(D("100000000000"), scale=8)


def test_per_quantity_allocation_cannot_redistribute_by_price() -> None:
    with pytest.raises(ValidationFailedError, match="quantity allocation"):
        calculate(
            (piece("a", "1000", "1"), piece("b", "10", "1")),
            (
                Component(
                    "fee",
                    ("a", "b"),
                    D(2),
                    effect="ADD",
                    kind="PER_QUANTITY",
                    quantity_basis="BILLED",
                    unit="PCS",
                ),
            ),
        )


def test_inclusive_rounding_is_visible_and_preserves_entered_consideration() -> None:
    result = calculate((Supply("s", D("0.07"), inclusive=True, taxes=gst("9")),))
    assert result.payable == D("0.07")
    assert result.commercial_total + result.charged_tax_total + result.rounding == result.payable
    assert result.lines[0].price_rounding == D("-0.01")


def test_gross_component_residual_keeps_exact_discount_consideration() -> None:
    line = Supply("s", D("1.18"), inclusive=True, taxes=gst("9"))
    discount = Component("d", ("s",), D("0.07"), kind="FIXED", basis="GROSS_INCL_TAX")
    result = calculate((line,), (discount,))
    assert result.payable == D("1.11")
    assert result.commercial_total + result.charged_tax_total + result.rounding == result.payable
