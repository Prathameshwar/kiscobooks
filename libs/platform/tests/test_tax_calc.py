"""India GST calculation mechanism (docs/tax-accounting-plan.md Phase 4).

Pure: no database. Every amount asserted here is a ``Decimal`` — driver or
arithmetic float coercion is silent, so the type is checked, not just the value.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from itertools import product

import pytest

from billing_platform.errors import ValidationFailedError
from billing_platform.money import RoundingMode
from billing_platform.tax_calc import (
    SNAPSHOT_SCHEMA_VERSION,
    ApportionBy,
    AssessableCharge,
    BuyerType,
    ChargeScope,
    ComponentCode,
    ComponentKind,
    ComponentRounding,
    PriceBasis,
    SupplyContext,
    SupplyDetermination,
    SupplyKind,
    SupplyReason,
    TaxComponent,
    TaxComputation,
    TaxLine,
    TaxRequest,
    Treatment,
    compute,
    place_of_supply,
)

D = Decimal
UT = frozenset({"04", "26", "31", "35", "38"})  # caller-supplied reference data in production
PIECE = uuid.UUID("01900000-0000-7000-8000-000000000001")
KILO = uuid.UUID("01900000-0000-7000-8000-000000000002")

INTRA = SupplyDetermination(SupplyContext.INTRA_STATE, False, SupplyReason.SAME_STATE)
INTRA_UT = SupplyDetermination(SupplyContext.INTRA_UT, False, SupplyReason.SAME_UT)
INTER = SupplyDetermination(SupplyContext.INTER_STATE, False, SupplyReason.DIFFERENT_STATE)
EXPORT = SupplyDetermination(SupplyContext.INTER_STATE, True, SupplyReason.EXPORT)


def pct(
    code: ComponentCode,
    rate: str,
    position: int,
    rounding: ComponentRounding = ComponentRounding.HALF_UP,
) -> TaxComponent:
    return TaxComponent(code, ComponentKind.PERCENT, rounding, position, percentage=D(rate))


def fixed_cess(amount: str, basis: str, position: int = 3, unit: uuid.UUID = PIECE) -> TaxComponent:
    return TaxComponent(
        ComponentCode.CESS,
        ComponentKind.FIXED_PER_UNIT,
        ComponentRounding.HALF_UP,
        position,
        amount=D(amount),
        currency="INR",
        unit_id=unit,
        basis_quantity=D(basis),
    )


def split(
    rate: str, rounding: ComponentRounding = ComponentRounding.HALF_UP
) -> tuple[TaxComponent, ...]:
    half = str(D(rate) / 2)
    return (pct(ComponentCode.CGST, half, 0, rounding), pct(ComponentCode.SGST, half, 1, rounding))


def igst(
    rate: str, rounding: ComponentRounding = ComponentRounding.HALF_UP
) -> tuple[TaxComponent, ...]:
    return (pct(ComponentCode.IGST, rate, 0, rounding),)


def line(
    value: str,
    components: tuple[TaxComponent, ...] = (),
    *,
    key: str = "L1",
    kind: SupplyKind = SupplyKind.GOODS,
    treatment: Treatment = Treatment.TAXABLE,
    basis: PriceBasis = PriceBasis.EXCLUSIVE,
    quantity: str | None = None,
    unit: uuid.UUID | None = None,
) -> TaxLine:
    return TaxLine(
        key,
        kind,
        D(value),
        treatment,
        components,
        basis,
        None if quantity is None else D(quantity),
        unit,
    )


def request(
    *lines: TaxLine,
    determination: SupplyDetermination = INTRA,
    precision: int = 2,
    may_charge_tax: bool = True,
    with_payment: bool = False,
    charges: tuple[AssessableCharge, ...] = (),
    rounding: RoundingMode = RoundingMode.HALF_UP,
) -> TaxRequest:
    return TaxRequest(
        lines=lines,
        determination=determination,
        currency="INR",
        amount_precision=precision,
        may_charge_tax=may_charge_tax,
        rounding_mode=rounding,
        zero_rated_with_payment=with_payment,
        charges=charges,
    )


def assert_decimals(result: TaxComputation) -> None:
    for row in result.lines:
        for value in (row.base_value, row.taxable_value, row.tax_total, row.gross):
            assert isinstance(value, Decimal)
        for comp in row.components:
            assert isinstance(comp.tax_amount, Decimal)
        for share in row.charges:
            assert isinstance(share.amount, Decimal)
    for total in result.component_totals:
        assert isinstance(total.tax_amount, Decimal)
    for value in vars_of(result):
        assert isinstance(value, Decimal)


def vars_of(result: TaxComputation) -> list[Decimal]:
    t = result.totals
    return [t.base_value, t.charges, t.taxable_value, t.tax_total, t.gross]


# --------------------------------------------------------------------------- place of supply


@pytest.mark.parametrize(
    ("supplier", "pos", "buyer", "context", "zero_rated", "reason"),
    [
        ("29", "29", "REGULAR", "INTRA_STATE", False, "SAME_STATE"),
        ("29", "27", "REGULAR", "INTER_STATE", False, "DIFFERENT_STATE"),
        ("04", "04", "UNREGISTERED", "INTRA_UT", False, "SAME_UT"),
        ("04", "29", "COMPOSITION", "INTER_STATE", False, "DIFFERENT_STATE"),
        ("29", "29", "OVERSEAS", "INTER_STATE", True, "EXPORT"),
        ("29", None, "REGULAR", "INTER_STATE", True, "EXPORT"),
        ("29", "29", "SEZ_UNIT", "INTER_STATE", True, "SEZ"),
        ("29", "27", "SEZ_DEVELOPER", "INTER_STATE", True, "SEZ"),
        (" 29", "29 ", "UIN", "INTRA_STATE", False, "SAME_STATE"),
    ],
)
def test_place_of_supply(
    supplier: str, pos: str | None, buyer: str, context: str, zero_rated: bool, reason: str
) -> None:
    result = place_of_supply(supplier, pos, buyer, utgst_states=UT)
    assert (result.context, result.zero_rated, result.reason) == (context, zero_rated, reason)


@pytest.mark.parametrize(
    ("supplier", "pos", "buyer"),
    [("", "29", "REGULAR"), ("29", "", "REGULAR"), ("29", "29", "RESELLER"), ("29", "29", 7)],
)
def test_place_of_supply_rejects_bad_input(supplier: str, pos: str, buyer: object) -> None:
    with pytest.raises(ValidationFailedError):
        place_of_supply(supplier, pos, buyer, utgst_states=UT)  # type: ignore[arg-type]  # hostile input


def test_determination_validates_its_fields() -> None:
    with pytest.raises(ValidationFailedError):
        SupplyDetermination("LOCAL", False, SupplyReason.SAME_STATE)  # type: ignore[arg-type]  # hostile input
    with pytest.raises(ValidationFailedError):
        SupplyDetermination(SupplyContext.INTRA_STATE, 1, SupplyReason.SAME_STATE)  # type: ignore[arg-type]  # hostile input
    assert BuyerType("NRTP") is BuyerType.NRTP


# --------------------------------------------------------------------------- core computation


@pytest.mark.parametrize(
    ("determination", "components", "expected"),
    [
        (INTRA, split("18"), [("CGST", "90.00"), ("SGST", "90.00")]),
        (
            INTRA_UT,
            (pct(ComponentCode.CGST, "6", 0), pct(ComponentCode.UTGST, "6", 1)),
            [("CGST", "60.00"), ("UTGST", "60.00")],
        ),
        (
            INTER,
            (*igst("28"), pct(ComponentCode.CESS, "12", 1)),
            [("IGST", "280.00"), ("CESS", "120.00")],
        ),
    ],
)
def test_exclusive_by_context(
    determination: SupplyDetermination,
    components: tuple[TaxComponent, ...],
    expected: list[tuple[str, str]],
) -> None:
    result = compute(request(line("1000", components), determination=determination))
    row = result.lines[0]
    assert [(c.component, c.tax_amount) for c in row.components] == [(c, D(a)) for c, a in expected]
    assert row.taxable_value == D("1000.00")
    assert row.gross == row.taxable_value + row.tax_total
    assert [(t.component, t.tax_amount) for t in result.component_totals] == [
        (c, D(a)) for c, a in expected
    ]
    assert_decimals(result)


@pytest.mark.parametrize(
    ("determination", "components"),
    [
        (INTRA, igst("18")),
        (INTER, split("18")),
        (INTRA_UT, split("18")),
        (INTRA, (pct(ComponentCode.CGST, "9", 0),)),
        (INTRA, (*split("18"), pct(ComponentCode.IGST, "18", 2))),
        (INTRA, (pct(ComponentCode.CESS, "1", 0),)),
    ],
)
def test_component_set_must_match_context(
    determination: SupplyDetermination, components: tuple[TaxComponent, ...]
) -> None:
    with pytest.raises(ValidationFailedError, match="supply context"):
        compute(request(line("100", components), determination=determination))


@pytest.mark.parametrize(
    "components",
    [
        (pct(ComponentCode.CGST, "9", 0), pct(ComponentCode.SGST, "6", 1)),
        (
            pct(ComponentCode.CGST, "9", 0),
            pct(ComponentCode.SGST, "9", 1, ComponentRounding.UP),
        ),
    ],
)
def test_central_and_state_share_rate_and_rounding(components: tuple[TaxComponent, ...]) -> None:
    with pytest.raises(ValidationFailedError, match="CGST|central"):
        compute(request(line("100", components)))


def test_taxable_line_without_components_is_rejected_when_tax_is_chargeable() -> None:
    with pytest.raises(ValidationFailedError, match="supply context"):
        compute(request(line("100")))


def test_composition_refuses_any_tax() -> None:
    with pytest.raises(ValidationFailedError, match="may not charge tax"):
        compute(request(line("100", split("5")), may_charge_tax=False))
    with pytest.raises(ValidationFailedError, match="may not charge tax"):
        compute(
            request(
                line(
                    "100",
                    (pct(ComponentCode.IGST, "0", 0), fixed_cess("1", "1")),
                    quantity="1",
                    unit=PIECE,
                ),
                determination=INTER,
                may_charge_tax=False,
            )
        )


def test_composition_without_components_and_with_zero_rates_is_allowed() -> None:
    result = compute(
        request(
            line("100"),
            line("50", split("0"), key="L2"),
            may_charge_tax=False,
        )
    )
    assert result.totals.tax_total == D("0.00")
    assert result.totals.gross == D("150.00")
    assert_decimals(result)


@pytest.mark.parametrize("treatment", [Treatment.NIL_RATED, Treatment.EXEMPT, Treatment.NON_GST])
def test_non_taxable_treatments(treatment: Treatment) -> None:
    result = compute(request(line("250.50", treatment=treatment)))
    row = result.lines[0]
    assert (row.taxable_value, row.tax_total, row.gross) == (D("250.50"), D("0.00"), D("250.50"))
    assert row.components == ()
    assert_decimals(result)
    if treatment is not Treatment.NIL_RATED:
        with pytest.raises(ValidationFailedError, match="carry no tax components"):
            compute(request(line("250.50", split("0"), treatment=treatment)))


@pytest.mark.parametrize("may_charge_tax", [True, False])
def test_nil_rated_accepts_zero_percent_components(may_charge_tax: bool) -> None:
    comps = (*split("0"), pct(ComponentCode.CESS, "0", 2))
    result = compute(
        request(
            line("250.50", comps, treatment=Treatment.NIL_RATED, basis=PriceBasis.INCLUSIVE),
            may_charge_tax=may_charge_tax,
        )
    )
    row = result.lines[0]
    assert (row.taxable_value, row.tax_total, row.gross) == (D("250.50"), D("0.00"), D("250.50"))
    assert [(c.component, c.percentage, c.tax_amount) for c in row.components] == [
        (ComponentCode.CGST, D("0"), D("0.00")),
        (ComponentCode.SGST, D("0"), D("0.00")),
        (ComponentCode.CESS, D("0"), D("0.00")),
    ]
    snap_components = result.snapshot()["lines"][0]["components"]  # type: ignore[index]  # snapshot is a JSON object
    assert [c["percentage"] for c in snap_components] == ["0.0000", "0.0000", "0.0000"]
    assert_decimals(result)


@pytest.mark.parametrize(
    ("components", "match"),
    [
        (split("5"), "only 0%"),
        ((*split("0"), pct(ComponentCode.CESS, "1", 2)), "only 0%"),
        ((*split("0"), fixed_cess("1", "1")), "only 0%"),
        (igst("0"), "supply context"),
        ((pct(ComponentCode.CGST, "0", 0),), "supply context"),
        (
            (
                pct(ComponentCode.CGST, "0", 0),
                pct(ComponentCode.SGST, "0", 1, ComponentRounding.UP),
            ),
            "central",
        ),
    ],
)
def test_nil_rated_rejects_non_zero_or_mismatched_components(
    components: tuple[TaxComponent, ...], match: str
) -> None:
    with pytest.raises(ValidationFailedError, match=match):
        compute(
            request(line("10", components, treatment=Treatment.NIL_RATED, quantity="1", unit=PIECE))
        )


def test_zero_rated_without_payment_records_rate_at_zero_amount() -> None:
    result = compute(
        request(
            line("1000", (*igst("18"), fixed_cess("400", "1000", 1)), quantity="250", unit=PIECE),
            determination=EXPORT,
        )
    )
    row = result.lines[0]
    assert [(c.percentage, c.amount, c.tax_amount) for c in row.components] == [
        (D("18"), None, D("0.00")),
        (None, D("400"), D("0.00")),
    ]
    assert row.gross == D("1000.00")
    assert result.snapshot()["zero_rated"] is True
    inclusive = compute(
        request(line("1000", igst("18"), basis=PriceBasis.INCLUSIVE), determination=EXPORT)
    )
    assert (inclusive.lines[0].taxable_value, inclusive.lines[0].tax_total) == (
        D("1000.00"),
        D("0.00"),
    )


def test_zero_rated_with_payment_charges_igst() -> None:
    result = compute(request(line("1000", igst("18")), determination=EXPORT, with_payment=True))
    assert result.lines[0].tax_total == D("180.00")
    assert result.snapshot()["zero_rated_with_payment"] is True


@pytest.mark.parametrize(
    ("value", "rounding", "expected"),
    [
        ("10.01", ComponentRounding.HALF_UP, "0.50"),
        ("10.01", ComponentRounding.UP, "0.51"),
        ("10.01", ComponentRounding.DOWN, "0.50"),
        ("10.10", ComponentRounding.HALF_UP, "0.51"),
        ("10.10", ComponentRounding.UP, "0.51"),
        ("10.10", ComponentRounding.DOWN, "0.50"),
        ("10.00", ComponentRounding.UP, "0.50"),
    ],
)
def test_component_rounding_modes(value: str, rounding: ComponentRounding, expected: str) -> None:
    result = compute(request(line(value, igst("5", rounding)), determination=INTER))
    assert result.lines[0].components[0].tax_amount == D(expected)


@pytest.mark.parametrize(
    ("precision", "value", "expected"),
    [(0, "999", "90"), (4, "10.0001", "0.9000"), (4, "10.0006", "0.9001"), (2, "999", "89.91")],
)
def test_precision(precision: int, value: str, expected: str) -> None:
    result = compute(request(line(value, split("18")), precision=precision))
    tax = result.lines[0].components[0].tax_amount
    assert tax == D(expected)
    assert tax.as_tuple().exponent == -precision
    assert_decimals(result)


def test_fixed_per_unit_cess_with_percent_cess() -> None:
    comps = (*split("28"), pct(ComponentCode.CESS, "5", 2), fixed_cess("4170", "1000", 3))
    result = compute(request(line("10000", comps, quantity="250", unit=PIECE)))
    amounts = {(c.component, c.kind): c.tax_amount for c in result.lines[0].components}
    assert amounts[(ComponentCode.CESS, ComponentKind.PERCENT)] == D("500.00")
    assert amounts[(ComponentCode.CESS, ComponentKind.FIXED_PER_UNIT)] == D("1042.50")
    assert result.component_totals[-1].tax_amount == D("1542.50")
    assert result.lines[0].gross == D("14342.50")


@pytest.mark.parametrize(("quantity", "unit"), [(None, PIECE), ("10", None), ("10", KILO)])
def test_fixed_cess_needs_quantity_in_its_unit(
    quantity: str | None, unit: uuid.UUID | None
) -> None:
    with pytest.raises(ValidationFailedError, match="quantity"):
        compute(
            request(line("100", (*split("28"), fixed_cess("1", "1")), quantity=quantity, unit=unit))
        )


# --------------------------------------------------------------------------- inclusive


def test_inclusive_back_calculation() -> None:
    result = compute(request(line("1180", split("18"), basis=PriceBasis.INCLUSIVE)))
    row = result.lines[0]
    assert (row.taxable_value, row.tax_total, row.gross) == (
        D("1000.00"),
        D("180.00"),
        D("1180.00"),
    )
    assert row.base_value == row.taxable_value


RATES = ["0.1", "0.25", "3", "5", "12", "18", "28"]


@pytest.mark.parametrize("precision", [0, 2, 4])
def test_inclusive_reconciles_exactly(precision: int) -> None:
    step = D(1).scaleb(-precision)
    amounts = [D(n) * step * 37 + step * k for n in range(0, 400, 23) for k in (0, 1, 3)]
    roundings = list(ComponentRounding)
    for amount, rate, rounding, with_cess in product(amounts, RATES, roundings, (False, True)):
        comps = split(rate, rounding) if rate not in ("0.1", "0.25") else igst(rate, rounding)
        determination = INTRA if len(comps) == 2 else INTER
        if with_cess:
            comps = (*comps, pct(ComponentCode.CESS, "12", 5, rounding), fixed_cess("0.5", "3", 6))
        gross = amount + 10
        result = compute(
            request(
                line(str(gross), comps, basis=PriceBasis.INCLUSIVE, quantity="2", unit=PIECE),
                determination=determination,
                precision=precision,
            )
        )
        row = result.lines[0]
        assert row.taxable_value + row.tax_total == gross
        assert row.gross == gross
        assert row.taxable_value >= 0
        assert isinstance(row.taxable_value, Decimal)


def test_inclusive_rejects_value_below_fixed_cess() -> None:
    with pytest.raises(ValidationFailedError, match="fixed cess exceeds"):
        compute(
            request(
                line(
                    "1",
                    (*split("5"), fixed_cess("10", "1")),
                    basis=PriceBasis.INCLUSIVE,
                    quantity="1",
                    unit=PIECE,
                )
            )
        )


def test_inclusive_rejects_value_that_cannot_carry_rounded_tax() -> None:
    comps = (
        pct(ComponentCode.CGST, "0.1", 0, ComponentRounding.UP),
        pct(ComponentCode.SGST, "0.1", 1, ComponentRounding.UP),
    )
    with pytest.raises(ValidationFailedError, match="cannot carry"):
        compute(request(line("0.01", comps, basis=PriceBasis.INCLUSIVE)))


# --------------------------------------------------------------------------- apportionment


def charge(
    amount: str,
    applies_to: ChargeScope = ChargeScope.GOODS,
    by: ApportionBy = ApportionBy.VALUE,
    key: str = "freight",
) -> AssessableCharge:
    return AssessableCharge(key, D(amount), applies_to, by)


def test_apportion_by_value_skips_ineligible_lines() -> None:
    result = compute(
        request(
            line("100", split("18"), key="A"),
            line("200", split("18"), key="B"),
            line("500", split("18"), key="S", kind=SupplyKind.SERVICE),
            charges=(charge("100"),),
        )
    )
    shares = {row.key: [s.amount for s in row.charges] for row in result.lines}
    assert shares == {"A": [D("33.33")], "B": [D("66.67")], "S": []}
    assert result.lines[0].taxable_value == D("133.33")
    assert result.lines[0].base_value == D("100.00")
    assert result.totals.charges == D("100.00")
    assert result.totals.taxable_value == D("900.00")
    assert_decimals(result)


def test_apportion_by_quantity_with_residual() -> None:
    result = compute(
        request(
            line("10", split("5"), key="A", kind=SupplyKind.SERVICE, quantity="1"),
            line("10", split("5"), key="B", quantity="1"),
            line("10", split("5"), key="C", quantity="1"),
            charges=(charge("100", ChargeScope.BOTH, ApportionBy.QUANTITY),),
        )
    )
    shares = [row.charges[0].amount for row in result.lines]
    assert shares == [D("33.33"), D("33.34"), D("33.33")]
    assert sum(shares) == D("100")


def test_apportion_never_negative_with_zero_weight_last_line() -> None:
    result = compute(
        request(
            line("1", split("5"), key="A"),
            line("1", split("5"), key="B"),
            line("0", split("5"), key="C"),
            charges=(charge("0.01"),),
        )
    )
    shares = [row.charges[0].amount for row in result.lines]
    assert sum(shares) == D("0.01")
    assert all(s >= 0 for s in shares)


def test_apportion_services_scope_and_zero_charge() -> None:
    result = compute(
        request(
            line("10", split("5"), key="G"),
            line("0", split("5"), key="S", kind=SupplyKind.SERVICE),
            charges=(charge("0", ChargeScope.SERVICES),),
        )
    )
    assert result.lines[1].charges[0].amount == D("0.00")


@pytest.mark.parametrize(
    ("lines", "charges", "match"),
    [
        ((line("10", split("5"), kind=SupplyKind.SERVICE),), (charge("1"),), "no line is eligible"),
        ((line("10", split("5")),), (charge("1", by=ApportionBy.QUANTITY),), "quantity"),
        ((line("0", split("5")),), (charge("1"),), "zero total weight"),
        ((line("10", split("5"), basis=PriceBasis.INCLUSIVE),), (charge("1"),), "tax-inclusive"),
        ((line("10", split("5")),), (charge("-1"),), "negative"),
    ],
)
def test_apportion_rejections(
    lines: tuple[TaxLine, ...], charges: tuple[AssessableCharge, ...], match: str
) -> None:
    with pytest.raises(ValidationFailedError, match=match):
        compute(request(*lines, charges=charges))


# --------------------------------------------------------------------------- validation


def _bad_component(**changes: object) -> TaxComponent:
    base: dict[str, object] = {
        "component": ComponentCode.CESS,
        "kind": ComponentKind.FIXED_PER_UNIT,
        "rounding_mode": ComponentRounding.HALF_UP,
        "position": 2,
        "amount": D("1"),
        "currency": "INR",
        "unit_id": PIECE,
        "basis_quantity": D("1"),
    }
    base.update(changes)
    return TaxComponent(**base)  # type: ignore[arg-type]  # hostile input


@pytest.mark.parametrize(
    ("components", "match"),
    [
        ((pct(ComponentCode.CGST, "9", 0), pct(ComponentCode.SGST, "9", 0)), "positions"),
        ((pct(ComponentCode.IGST, "18", 16),), "position"),
        ((pct(ComponentCode.IGST, "101", 0),), "100"),
        ((pct(ComponentCode.IGST, "-1", 0),), "negative"),
        ((pct(ComponentCode.IGST, "1.00001", 0),), "representable"),
        ((_bad_component(component=ComponentCode.IGST, position=0),), "only cess"),
        ((*igst("18"), _bad_component(currency="USD")), "currency"),
        ((*igst("18"), _bad_component(basis_quantity=None)), "fixed cess needs"),
        ((*igst("18"), _bad_component(amount=D("0"))), "positive"),
        (
            (*igst("18"), _bad_component(kind=ComponentKind.PERCENT, percentage=D("1"))),
            "only a percentage",
        ),
        ((*igst("18"), _bad_component(kind=ComponentKind.PERCENT)), "only a percentage"),
        (tuple(pct(ComponentCode.CESS, "1", i) for i in range(17)), "too many"),
    ],
)
def test_component_validation(components: tuple[TaxComponent, ...], match: str) -> None:
    with pytest.raises(ValidationFailedError, match=match):
        compute(request(line("100", components, quantity="1", unit=PIECE), determination=INTER))


def test_unknown_vocabulary_is_rejected() -> None:
    with pytest.raises(ValidationFailedError, match="ComponentCode"):
        TaxComponent("VAT", ComponentKind.PERCENT, ComponentRounding.UP, 0, percentage=D(1))  # type: ignore[arg-type]  # hostile input
    with pytest.raises(ValidationFailedError, match="ComponentRounding"):
        pct(ComponentCode.IGST, "1", 0, "HALF_EVEN")  # type: ignore[arg-type]  # hostile input
    with pytest.raises(ValidationFailedError, match="Treatment"):
        line("1", treatment="ZERO")  # type: ignore[arg-type]  # hostile input
    with pytest.raises(ValidationFailedError, match="ApportionBy"):
        charge("1", by="WEIGHT")  # type: ignore[arg-type]  # hostile input
    # Replica strings coerce to the vocabulary.
    assert line("1", kind="SERVICE").supply_kind is SupplyKind.SERVICE  # type: ignore[arg-type]  # replica string


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"amount_precision": 5}, "precision"),
        ({"amount_precision": True}, "precision"),
        ({"currency": "inr"}, "currency"),
        ({"currency": "RUPEE"}, "currency"),
        ({"may_charge_tax": 1}, "boolean"),
        ({"determination": "INTRA"}, "determination"),
        ({"lines": ()}, "lines"),
        ({"lines": (line("1", split("5")), line("1", split("5")))}, "unique"),
        ({"lines": (line("1", split("5"), key=""),)}, "keys"),
        ({"charges": tuple(charge("1", key=f"c{i}") for i in range(65))}, "too many"),
        ({"lines": (line("-1", split("5")),)}, "negative"),
        ({"lines": (line("1.005", split("5")),)}, "representable"),
        ({"lines": (line("1", split("5"), quantity="-1"),)}, "negative"),
        ({"lines": (line("999999999999999", split("28")),)}, "DECIMAL"),
    ],
)
def test_request_validation(changes: dict[str, object], match: str) -> None:
    base: dict[str, object] = {
        "lines": (line("100", split("5")),),
        "determination": INTRA,
        "currency": "INR",
        "amount_precision": 2,
        "may_charge_tax": True,
    }
    base.update(changes)
    with pytest.raises(ValidationFailedError, match=match):
        compute(TaxRequest(**base))  # type: ignore[arg-type]  # hostile input


def test_document_rounding_mode_drives_inclusive_estimate() -> None:
    for mode in RoundingMode:
        result = compute(
            request(line("100.01", split("18"), basis=PriceBasis.INCLUSIVE), rounding=mode)
        )
        row = result.lines[0]
        assert row.taxable_value + row.tax_total == D("100.01")
    with pytest.raises(ValidationFailedError, match="RoundingMode"):
        request(line("1"), rounding="ceiling")  # type: ignore[arg-type]  # hostile input


def test_half_even_document_rounding_in_apportionment() -> None:
    result = compute(
        request(
            line("1", split("5"), key="A"),
            line("1", split("5"), key="B"),
            line("2", split("5"), key="C"),
            charges=(charge("0.10"),),
            rounding=RoundingMode.HALF_EVEN,
        )
    )
    # Cumulative targets 0.025 -> 0.02 (even), 0.05, 0.10.
    assert [row.charges[0].amount for row in result.lines] == [D("0.02"), D("0.03"), D("0.05")]


# --------------------------------------------------------------------------- snapshot


def test_snapshot_is_versioned_and_json_safe() -> None:
    result = compute(
        request(
            line("10000", (*split("28"), fixed_cess("4170", "1000")), quantity="250", unit=PIECE),
            line("100", key="X", treatment=Treatment.EXEMPT),
            charges=(charge("50"),),
        )
    )
    snap = result.snapshot()
    assert snap["schema_version"] == SNAPSHOT_SCHEMA_VERSION == 1
    assert json.loads(json.dumps(snap)) == snap
    assert snap["context"] == "INTRA_STATE"
    assert snap["rounding_mode"] == "half_up"
    first = snap["lines"][0]  # type: ignore[index]  # snapshot is a JSON object
    assert first["charges"] == [{"key": "freight", "amount": "49.50"}]
    assert first["components"][2]["unit_id"] == str(PIECE)
    assert first["components"][0]["amount"] is None
    totals = snap["totals"]
    assert totals == {
        "base_value": "10100.00",
        "charges": "50.00",
        "taxable_value": "10150.00",
        "tax_total": str(result.totals.tax_total),
        "gross": str(result.totals.gross),
    }
    assert result.totals.gross == result.totals.taxable_value + result.totals.tax_total


def test_compute_is_deterministic() -> None:
    req = request(
        line("123.45", split("12"), key="A", quantity="3"),
        line("67.89", split("12"), key="B", quantity="5"),
        charges=(charge("10.01", by=ApportionBy.QUANTITY),),
    )
    assert compute(req) == compute(req)
    assert compute(req).snapshot() == compute(req).snapshot()
