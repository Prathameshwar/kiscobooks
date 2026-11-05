"""Independent statutory examples; no expected values copied from the calculator."""

import datetime as dt
from decimal import Decimal

import pytest

from reports.domain.gstr3b import amounts, calculate, period_bounds


def record(category, **values):
    return {
        "category": category,
        "return_date": "2026-10-01",
        "registration_id": "reg",
        "reference": "proof",
        "evidence_hash": "a" * 64,
        "source_id": category,
        "taxable": "0",
        "igst": "0",
        "cgst": "0",
        "sgst": "0",
        "cess": "0",
        **values,
    }


def run(*records):
    return calculate(
        list(records),
        {
            "id": "reg",
            "number": "27ABCDE1234F1Z5",
            "regime": "regular",
            "jurisdiction_code": "IN-MH",
        },
        dt.date(2026, 10, 1),
        dt.date(2026, 10, 31),
    )


def test_statutory_period_is_independent_of_accounting_year():
    assert period_bounds("2026-10", "MONTHLY") == (dt.date(2026, 10, 1), dt.date(2026, 10, 31))
    assert period_bounds("2026-Q4", "QRMP") == (dt.date(2026, 10, 1), dt.date(2026, 12, 31))
    with pytest.raises(ValueError):
        period_bounds("2026-10", "QRMP")


def test_exact_amounts_reject_float_and_implicit_storage_rounding():
    assert amounts(record("3.1a", taxable="12.1234"))["taxable"] == Decimal("12.1234")
    for bad in (12.1, "NaN", "1.12345", "1000000000000000"):
        with pytest.raises(ValueError):
            amounts(record("3.1a", taxable=bad))


def test_outward_returns_and_disclosures_do_not_double_tax_liability():
    result = run(
        record("3.1a", taxable="1000", igst="180"),
        record("3.1a", taxable="-100", igst="-18"),
        record("3.2", taxable="900", igst="162", place_of_supply="29", recipient="UNREGISTERED"),
        record("3.1.1ii", taxable="300"),
    )
    assert result["form"]["3.1a"]["igst"] == "162.00"
    assert result["payment"]["IGST"]["normal_liability"] == "162.00"
    assert result["form"]["3.1.1ii"]["taxable"] == "300.00"


def test_itc_claims_reversals_reclaims_and_ineligible_disclosure():
    result = run(
        record("4A5", cgst="100", sgst="100"),
        record("4B1", cgst="10", sgst="10"),
        record("4B2", cgst="20", sgst="20"),
        record("4D1", cgst="5", sgst="5"),
        record("4D2", cgst="7", sgst="7"),
    )
    assert result["form"]["4C"]["cgst"] == "70.00"
    assert result["form"]["4D1"]["cgst"] == "5.00"
    assert result["form"]["4D2"]["cgst"] == "7.00"


def test_cash_deposit_is_not_an_offset_and_rcm_cannot_use_credit():
    result = run(
        record("3.1d", igst="90"),
        record("CASH_DEPOSIT", igst="90"),
        record("OFFSET_RCM_ITC", igst="90"),
    )
    assert result["payment"]["IGST"]["rcm_unpaid"] == "90.00"
    assert any(issue["code"] == "CASH_ONLY" for issue in result["issues"])


def test_missing_coverage_is_attention_not_a_nil_return():
    result = run()
    assert result["status"] == "NEEDS_ATTENTION"
    assert result["nil"] is False
    assert any(issue["code"] == "SOURCE_COVERAGE" for issue in result["issues"])


def test_table_five_has_statutory_interstate_and_intrastate_columns():
    result = run(record("5_EXEMPT_INTER", taxable="25"), record("5_NONGST_INTRA", taxable="10"))
    assert result["inward_rows"] == [
        {
            "nature": "Supplies from composition taxpayers, exempt and nil rated supplies",
            "interstate": "25.00",
            "intrastate": "0.00",
        },
        {"nature": "Non-GST supply", "interstate": "0.00", "intrastate": "10.00"},
    ]


def test_invalid_pos_and_disclosures_exceeding_outward_are_exceptions():
    result = run(
        record("3.2", taxable="50", igst="9", place_of_supply="90", recipient="UNREGISTERED")
    )
    assert any(row["code"] == "PLACE_OF_SUPPLY" for row in result["issues"])
    result = run(
        record("3.2", taxable="50", igst="9", place_of_supply="29", recipient="UNREGISTERED")
    )
    assert any(row["code"] == "DISCLOSURE_EXCEEDS_OUTWARD" for row in result["issues"])


def test_complete_portal_coverage_requires_retained_import_even_for_zero():
    result = run(record("COVERAGE", coverage_area="GSTR1", coverage_status="COMPLETE"))
    assert any(row["code"] == "PORTAL_EVIDENCE_MISSING" for row in result["issues"])


def test_credit_must_cover_its_own_tax_head_before_cross_head_utilisation():
    result = run(
        record("3.1a", igst="100", cgst="100"),
        record("OPENING_ITC", cgst="100"),
        record("OFFSET_NORMAL_ITC", credit_head="CGST", igst="100"),
    )
    assert any(row["code"] == "OWN_HEAD_FIRST" for row in result["issues"])


def test_interstate_state_rows_are_validated_and_advances_excluded_since_oct2025():
    result = run(
        record("3.2", taxable="100", igst="18", place_of_supply="27", recipient="UNREGISTERED"),
        record(
            "3.2",
            taxable="100",
            igst="18",
            place_of_supply="29",
            recipient="UNREGISTERED",
            is_advance=True,
        ),
    )
    assert result["pos_rows"] == []
    assert any(issue["code"] == "PLACE_OF_SUPPLY" for issue in result["issues"])


@pytest.mark.parametrize(
    "category",
    [
        "3.1b",
        "3.1c",
        "3.1e",
        "3.1.1ii",
        "5_EXEMPT_INTER",
        "5_EXEMPT_INTRA",
        "5_NONGST_INTER",
        "5_NONGST_INTRA",
    ],
)
def test_statutory_disclosures_retain_taxable_value(category):
    result = run(record(category, taxable="125.55"))
    assert result["form"][category]["taxable"] == "125.55"
    assert result["nil"] is False


def test_normal_credit_cash_and_rcm_offsets_reconcile_independently():
    result = run(
        record("3.1a", taxable="1000", igst="180"),
        record("3.1d", igst="90"),
        record("4A5", igst="100"),
        record("CASH_DEPOSIT", igst="170"),
        record("OFFSET_NORMAL_ITC", igst="100", credit_head="IGST"),
        record("OFFSET_NORMAL_CASH", igst="80"),
        record("OFFSET_RCM_CASH", igst="90"),
    )
    assert result["payment"]["IGST"]["normal_unpaid"] == "0.00"
    assert result["payment"]["IGST"]["rcm_unpaid"] == "0.00"
    assert result["payment"]["IGST"]["closing_cash"] == "0.00"


def test_credit_cross_use_and_igst_first_are_reported():
    result = run(
        record("OPENING_ITC", igst="10", cgst="10"),
        record("OFFSET_NORMAL_ITC", sgst="10", credit_head="CGST"),
    )
    codes = {issue["code"] for issue in result["issues"]}
    assert {"ITC_UTILISATION", "IGST_FIRST"} <= codes


def test_rule_precision_rounds_total_once():
    result = run(record("3.1a", taxable="0.0050"), record("3.1a", taxable="0.0050"))
    assert result["form"]["3.1a"]["taxable"] == "0.01"


def test_nil_requires_explicit_coverage_and_no_operational_records():
    from reporting_contract.gst import COVERAGE_AREAS

    coverage = [
        record("COVERAGE", coverage_area=area, coverage_status="NOT_APPLICABLE")
        for area in COVERAGE_AREAS
    ]
    assert run(*coverage)["nil"] is True
    assert run(*coverage, record("3.1a"))["nil"] is False


def test_historical_balances_do_not_disqualify_an_otherwise_nil_return():
    from reporting_contract.gst import COVERAGE_AREAS

    coverage = [
        record(
            "COVERAGE",
            coverage_area=area,
            coverage_status="COMPLETE" if area == "OPENING" else "NOT_APPLICABLE",
        )
        for area in COVERAGE_AREAS
    ]
    result = run(
        *coverage,
        record("OPENING_CASH", igst="100"),
        record("OPENING_ITC", igst="50"),
        record("PREVIOUS_RETURN", igst="20"),
    )
    assert result["status"] == "DRAFT"
    assert result["nil"] is True
    assert run(*coverage, record("GSTR2B", igst="20"))["nil"] is False


def test_import_goods_cells_follow_statutory_heads():
    result = run(record("4A1", igst="180", cess="10"))
    assert result["form"]["4A1"]["igst"] == "180.00"
    assert result["form"]["4A1"]["cgst"] is None
    assert result["form"]["4A1"]["sgst"] is None


def test_not_applicable_coverage_cannot_hide_recorded_gst_activity():
    from reporting_contract.gst import COVERAGE_AREAS

    coverage = [
        record("COVERAGE", coverage_area=area, coverage_status="NOT_APPLICABLE")
        for area in COVERAGE_AREAS
    ]
    result = run(
        *coverage,
        record("3.1a", taxable="1000", igst="180"),
        record("4A5", igst="180"),
    )
    assert result["status"] == "NEEDS_ATTENTION"
    assert any(row["code"] == "COVERAGE_NOT_APPLICABLE" for row in result["issues"])


def test_statutory_totals_add_the_displayed_child_cells():
    result = run(
        record("4A1", igst="0.0050"),
        record("4A5", igst="0.0050"),
        record("4B2", igst="0.0050"),
        record("3.1a", igst="0.0050"),
        record("3.1b", igst="0.0050"),
    )
    assert result["form"]["4A1"]["igst"] == "0.01"
    assert result["form"]["4A5"]["igst"] == "0.01"
    assert result["form"]["4A"]["igst"] == "0.02"
    assert result["form"]["4C"]["igst"] == "0.01"
    assert result["payment"]["IGST"]["normal_liability"] == "0.02"


def test_eco_interstate_disclosures_are_included_without_double_liability():
    result = run(
        record("3.1.1i", taxable="1000", igst="180"),
        record("3.2", taxable="1000", igst="180", place_of_supply="29", recipient="UNREGISTERED"),
    )
    assert not any(row["code"] == "DISCLOSURE_EXCEEDS_OUTWARD" for row in result["issues"])
    assert result["payment"]["IGST"]["normal_liability"] == "0.00"
    assert result["payment"]["IGST"]["eco_liability"] == "180.00"


@pytest.mark.parametrize("conflict", [False, True])
async def test_coverage_uses_the_frozen_sequence_and_rejects_conflicting_latest_proofs(conflict):
    from reporting_contract.gst import COVERAGE_AREAS

    proofs = [
        record(
            "COVERAGE", coverage_area=area, coverage_status="NOT_APPLICABLE", covered_sequence=10
        )
        for area in COVERAGE_AREAS
    ]
    proofs.append(
        record(
            "COVERAGE",
            coverage_area="OPENING",
            coverage_status="COMPLETE",
            covered_sequence=9,
            return_date="2026-10-30",
        )
    )
    if conflict:
        proofs.append(
            record(
                "COVERAGE",
                coverage_area="OPENING",
                coverage_status="COMPLETE",
                covered_sequence=10,
                return_date="2026-10-20",
            )
        )
    value = calculate(
        proofs,
        {"id": "reg", "number": "27ABCDE1234F1Z5"},
        dt.date(2026, 10, 1),
        dt.date(2026, 10, 31),
        sequence=10,
    )
    assert not any(row["code"] == "STALE_COVERAGE" for row in value["issues"])
    assert any(row["code"] == "COVERAGE_CONFLICT" for row in value["issues"]) is conflict
    if not conflict:
        assert value["status"] == "DRAFT"


def test_cash_payment_cannot_bypass_own_tax_head_credit_priority():
    value = run(
        record("3.1a", igst="100", cgst="100"),
        record("OPENING_ITC", igst="100"),
        record("CASH_DEPOSIT", igst="100"),
        record("OFFSET_NORMAL_CASH", igst="100"),
        record("OFFSET_NORMAL_ITC", credit_head="IGST", cgst="100"),
    )
    assert value["payment"]["IGST"]["normal_unpaid"] == "0.00"
    assert any(row["code"] == "OWN_HEAD_FIRST" for row in value["issues"])
