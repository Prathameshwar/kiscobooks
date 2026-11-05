import datetime as dt
import uuid
from decimal import Decimal

import pytest
from reporting_contract.gst_outward import AREAS, GstOutwardRecord

from reports.domain.gstr1 import calculate


def test_b2cs_statutory_grouping_retains_exact_sources_before_rounding():
    sources = [
        document(
            amount="0.004",
            igst="0",
            document_number="S-" + str(index),
            details={"recipient_type": "UNREGISTERED", "recipient_gstin": None},
        )
        for index in (1, 2)
    ]
    rows, evidence = run(sources)
    grouped = [row for row in rows if row["table"] == "7" and row["row_role"] == "STATUTORY"]
    assert len(grouped) == 1
    assert grouped[0]["taxable"] == evidence["form"]["7"]["taxable"] == "0.01"
    assert grouped[0]["source_count"] == 2
    assert len(grouped[0]["source_records"]) == 2
    assert sum(
        Decimal(row["signed_amounts"]["taxable"])
        for row in rows
        if row["table"] == "7" and row["row_role"] == "SOURCE"
    ) == Decimal("0.008")


def test_registered_invoice_groups_lines_at_each_rate_before_rounding():
    invoice = document(
        details={"items": [{"taxable": "0.004", "hsn": "9983", "rate": "0", "uqc": "NA"}] * 2}
    )
    rows, evidence = run([invoice])
    invoices = [row for row in rows if row["table"] == "4A"]
    grouped = next(row for row in invoices if row["row_role"] != "LINE")
    assert grouped["taxable"] == evidence["form"]["4A"]["taxable"] == "0.01"
    assert evidence["table_counts"]["4A"] == 1
    assert len([row for row in invoices if row["row_role"] == "LINE"]) == 2


def test_exempt_statutory_format_separates_treatments_and_location():
    sources = [
        document(
            amount="100",
            igst="0",
            document_number="E-" + str(index),
            details={
                "items": [{"taxable": "100", "hsn": "9983", "uqc": "NA", "treatment": treatment}]
            },
        )
        for index, treatment in enumerate(("NIL_RATED", "EXEMPT", "NON_GST"), 1)
    ]
    rows, evidence = run(sources)
    grouped = next(row for row in rows if row["table"] == "8" and row["row_role"] == "STATUTORY")
    assert grouped["nil_rated"] == grouped["exempt"] == grouped["non_gst"] == "100.00"
    assert grouped["supply_location"] == "INTER_STATE"
    assert evidence["form"]["8"]["taxable"] == "300.00"


def test_document_series_must_cover_the_retained_invoice():
    records = coverage([document()])
    series = next(row for row in records if row["kind"] == "DOCUMENTS")
    series["details"] |= {"serial_from": "OTHER-1", "serial_to": "OTHER-1"}
    _, evidence = calculate(records, REG, START, END, sequence=10)
    assert any(row["code"] == "DOCUMENT_SERIES_MEMBERSHIP" for row in evidence["issues"])


def test_document_only_activity_is_not_nil():
    records = coverage([document()])
    records = [row for row in records if row["kind"] != "INVOICE"]
    _, evidence = calculate(records, REG, START, END, sequence=10)
    assert not evidence["nil"]


def test_fx_conversion_requires_complete_evidence_and_exact_inr_value():
    fx = document(
        details={
            "source_currency": "USD",
            "source_invoice_value": "14.75",
            "conversion_rate": "80",
            "conversion_date": "2026-10-01",
            "conversion_reference": "Retained exchange rate",
        }
    )
    rows, evidence = run([fx])
    assert rows[0]["source_currency"] == "USD"
    assert rows[0]["source_invoice_value"] == "14.7500"
    assert evidence["status"] == "DRAFT"
    with pytest.raises(ValueError):
        document(details={"source_currency": "USD"})
    with pytest.raises(ValueError):
        document(
            details={
                "source_currency": "USD",
                "source_invoice_value": "14.75",
                "conversion_rate": "81",
                "conversion_date": "2026-10-01",
                "conversion_reference": "Wrong rate",
            }
        )


START, END = dt.date(2026, 10, 1), dt.date(2026, 10, 31)


def test_completeness_proof_cannot_claim_a_future_source_sequence():
    _, evidence = calculate(coverage([document()], sequence=11), REG, START, END, sequence=10)
    assert any(row["code"].startswith("COVERAGE_STALE_") for row in evidence["issues"])


REG = {
    "id": str(uuid.uuid4()),
    "number": "27ABCDE1234F1Z5",
    "country_code": "IN",
    "tax_system": "gst_in",
    "regime": "regular",
    "valid_from": "2025-01-01",
    "outward_profiles": [
        {
            "valid_from": "2026-04-01",
            "valid_to": None,
            "annual_turnover": "40000000.0000",
            "rule_14a": False,
        }
    ],
}


def document(*, amount="1000", igst="180", cgst="0", sgst="0", details=None, **extra):
    from decimal import Decimal

    nested = {
        "place_of_supply": "24",
        "recipient_type": "REGISTERED",
        "recipient_gstin": "24ABCDE1234F1Z5",
        "recipient_name": "Fixture recipient",
        "items": [
            {
                "taxable": amount,
                "igst": igst,
                "cgst": cgst,
                "sgst": sgst,
                "hsn": "9983",
                "rate": "18",
                "uqc": "NA",
            }
        ],
        **(details or {}),
    }
    value = {
        "registration_id": REG["id"],
        "return_date": START.isoformat(),
        "document_date": START.isoformat(),
        "kind": "INVOICE",
        "document_number": "INV-1",
        "source_entity": "EXTERNAL",
        "reference": "Fixture retained invoice",
        "evidence_hash": "a" * 64,
        "explanation": "Explicit test-only statutory evidence",
        "invoice_value": str(
            sum(
                Decimal(item.get(head, "0"))
                for item in nested["items"]
                for head in ("taxable", "igst", "cgst", "sgst", "cess")
            )
        ),
        "details": nested,
        **extra,
    }
    return GstOutwardRecord.model_validate(value).model_dump(mode="json") | {
        "id": str(uuid.uuid4())
    }


def coverage(records, *, sequence=10):
    output = list(records)
    for area in AREAS:
        value = {
            "registration_id": REG["id"],
            "return_date": START.isoformat(),
            "document_date": START.isoformat(),
            "kind": "COVERAGE",
            "source_entity": "EXTERNAL",
            "reference": "Reviewed " + area,
            "evidence_hash": "b" * 64,
            "explanation": "Complete source review",
            "details": {
                "coverage_area": area,
                "coverage_status": "COMPLETE",
                "covered_sequence": sequence,
            },
        }
        output.append(
            GstOutwardRecord.model_validate(value).model_dump(mode="json")
            | {"id": str(uuid.uuid4())}
        )
    categories = {
        "INVOICE": "OUTWARD_INVOICE",
        "CREDIT_NOTE": "CREDIT_NOTE",
        "DEBIT_NOTE": "DEBIT_NOTE",
        "ADVANCE": "RECEIPT_VOUCHER",
    }
    for category in {categories.get(row["kind"]) for row in records} - {None}:
        members = {
            row["document_number"] for row in records if categories.get(row["kind"]) == category
        }
        value = {
            "registration_id": REG["id"],
            "return_date": START.isoformat(),
            "document_date": START.isoformat(),
            "kind": "DOCUMENTS",
            "source_entity": "EXTERNAL",
            "reference": "Actual series " + category,
            "evidence_hash": "c" * 64,
            "explanation": "Actual issued series",
            "details": {
                "document_category": category,
                "serial_from": sorted(members)[0],
                "serial_to": sorted(members)[-1],
                "total_count": len(members),
            },
        }
        output.append(
            GstOutwardRecord.model_validate(value).model_dump(mode="json")
            | {"id": str(uuid.uuid4())}
        )
    return output


def run(records, **options):
    return calculate(coverage(records), REG, START, END, sequence=10, **options)


def test_registered_invoices_hsn_documents_and_bridge_count_liability_once():
    rows, evidence = run([document()])
    assert evidence["status"] == "DRAFT", evidence["issues"]
    assert evidence["form"]["4A"]["igst"] == "180.00"
    assert evidence["form"]["12_B2B"]["igst"] == "180.00"
    assert evidence["bridge"]["3.1a"]["igst"] == "180.00"
    assert evidence["document_count"] == 1
    assert not evidence["nil"]
    assert len(rows) == 3


@pytest.mark.parametrize(
    ("amount", "igst", "pos", "expected"),
    [
        ("100000", "0", "24", "7"),
        ("100001", "0", "24", "5"),
        ("90000", "16200", "24", "5"),
        ("200000", "0", "27", "7"),
    ],
)
def test_b2c_full_invoice_value_and_strict_boundary(amount, igst, pos, expected):
    _, evidence = run(
        [
            document(
                amount=amount,
                igst=igst,
                details={
                    "recipient_type": "UNREGISTERED",
                    "recipient_gstin": None,
                    "place_of_supply": pos,
                },
            )
        ]
    )
    assert evidence["form"][expected]["taxable"] == amount + ".00"


@pytest.mark.parametrize(
    ("supply", "expected"),
    [
        ("EXPORT_WPAY", "6A"),
        ("EXPORT_WOPAY", "6A"),
        ("SEZ_WPAY", "6B"),
        ("SEZ_WOPAY", "6B"),
        ("DEEMED_EXPORT", "6C"),
    ],
)
def test_special_supplies_are_explicit(supply, expected):
    details = {"supply_type": supply, "export_reference": "Retained statutory approval"}
    if supply.startswith("EXPORT"):
        details |= {
            "recipient_type": "UNREGISTERED",
            "recipient_gstin": None,
            "place_of_supply": "96",
        }
    _, evidence = run([document(igst="0" if supply.endswith("WOPAY") else "180", details=details)])
    assert evidence["status"] == "DRAFT", evidence["issues"]
    assert evidence["form"][expected]["taxable"] == "1000.00"


def test_supplier_eco_disclosures_do_not_duplicate_normal_tax():
    _, evidence = run(
        [document(details={"eco_scheme": "TCS", "operator_gstin": "27AAAAA0000A1Z5"})]
    )
    assert evidence["form"]["4A"]["igst"] == evidence["form"]["14_TCS"]["igst"] == "180.00"
    assert evidence["bridge"]["3.1a"]["igst"] == "180.00"
    _, supplied = run(
        [document(details={"eco_scheme": "9_5", "operator_gstin": "27AAAAA0000A1Z5"})]
    )
    assert supplied["form"]["4A"]["igst"] == "0.00"
    assert supplied["bridge"]["3.1a"]["igst"] == "0.00"
    assert supplied["bridge"]["3.1.1ii"]["igst"] == "180.00"


@pytest.mark.parametrize(
    ("supplier", "recipient", "expected"),
    [
        ("REGISTERED", "REGISTERED", "15_B2B"),
        ("REGISTERED", "UNREGISTERED", "15_B2C"),
        ("UNREGISTERED", "REGISTERED", "15_URP2B"),
        ("UNREGISTERED", "UNREGISTERED", "15_URP2C"),
    ],
)
def test_eco_operator_roles(supplier, recipient, expected):
    value = document(
        kind="ECO_OPERATOR",
        details={
            "eco_scheme": "9_5",
            "operator_gstin": REG["number"],
            "supplier_type": supplier,
            "supplier_gstin": "24AAAAA0000A1Z5" if supplier == "REGISTERED" else None,
            "recipient_type": recipient,
            "recipient_gstin": "24ABCDE1234F1Z5" if recipient == "REGISTERED" else None,
        },
    )
    _, evidence = run([value])
    assert evidence["form"][expected]["igst"] == "180.00"
    assert evidence["bridge"]["3.1.1i"]["igst"] == "180.00"
    assert evidence["bridge"]["3.1a"]["igst"] == "0.00"


def test_b2cs_credit_note_nets_once_and_commercial_note_has_no_tax_effect():
    invoice = document(details={"recipient_type": "UNREGISTERED", "recipient_gstin": None})
    note = document(
        amount="100",
        igst="18",
        kind="CREDIT_NOTE",
        document_number="CN-1",
        original_record_id=invoice["id"],
        details={"recipient_type": "UNREGISTERED", "recipient_gstin": None},
    )
    _, evidence = run([invoice, note])
    assert evidence["form"]["7"]["taxable"] == "900.00"
    assert evidence["form"]["9B_UNREG"]["igst"] == "0.00"
    assert evidence["bridge"]["3.1a"]["igst"] == "162.00"
    note["details"]["tax_note"] = False
    _, evidence = run([invoice, note])
    assert evidence["bridge"]["3.1a"]["igst"] == "180.00"


def test_amendment_full_revised_display_and_net_differential_bridge():
    original = document(return_date="2026-09-01", document_date="2026-09-01")
    revised = document(
        amount="1100",
        igst="198",
        kind="AMENDMENT",
        original_record_id=original["id"],
        details={
            "original_filing_reference": "Filed original ARN",
            "original_filing_hash": "d" * 64,
            "annual_return_checked": True,
        },
    )
    _, evidence = run([revised], originals={original["id"]: original})
    assert evidence["status"] == "DRAFT", evidence["issues"]
    assert evidence["form"]["9A_B2B"]["taxable"] == "100.00"
    assert evidence["bridge"]["3.1a"]["taxable"] == "100.00"
    assert evidence["bridge"]["3.1a"]["igst"] == "18.00"
    assert evidence["form"]["12_B2B"]["igst"] == "18.00"


def amendment(original, amount, igst, *, return_date="2026-10-01", details=None):
    return document(
        amount=amount,
        igst=igst,
        kind="AMENDMENT",
        original_record_id=original["id"],
        return_date=return_date,
        document_date=original["document_date"],
        details={
            "original_filing_reference": "Actual prior return proof",
            "original_filing_hash": "d" * 64,
            "annual_return_checked": True,
            **(details or {}),
        },
    )


def test_repeated_amendment_uses_the_previous_revision_and_retains_its_history():
    original = document(return_date="2026-08-01", document_date="2026-08-01")
    previous = amendment(original, "1100", "198", return_date="2026-09-01")
    revised = amendment(previous, "1200", "216")
    rows, evidence = run([revised], originals={row["id"]: row for row in (original, previous)})
    assert evidence["status"] == "DRAFT", evidence["issues"]
    assert (
        evidence["form"]["9A_B2B"]["taxable"] == evidence["bridge"]["3.1a"]["taxable"] == "100.00"
    )
    assert evidence["bridge"]["3.1a"]["igst"] == "18.00"
    assert next(row for row in rows if row["table"] == "9A_B2B")["amendment_chain"] == [
        previous["id"],
        original["id"],
    ]


def test_reusing_an_obsolete_amendment_baseline_is_not_ready():
    original = document(return_date="2026-08-01", document_date="2026-08-01")
    previous = amendment(original, "1100", "198", return_date="2026-09-01")
    revised = amendment(original, "1200", "216")
    _, evidence = run([revised], originals={row["id"]: row for row in (original, previous)})
    assert "AMENDMENT_BASELINE_STALE" in {row["code"] for row in evidence["issues"]}
    assert evidence["bridge"]["3.1a"]["taxable"] == "0.00"


def test_amended_b2cl_credit_note_keeps_its_note_table_and_negative_bridge():
    invoice = document(
        amount="200000",
        igst="36000",
        return_date="2026-08-01",
        document_date="2026-08-01",
        details={"recipient_type": "UNREGISTERED", "recipient_gstin": None},
    )
    note = document(
        amount="1000",
        igst="180",
        kind="CREDIT_NOTE",
        document_number="CN-1",
        original_record_id=invoice["id"],
        return_date="2026-09-01",
        document_date="2026-09-01",
        details={
            "recipient_type": "UNREGISTERED",
            "recipient_gstin": None,
            "annual_return_checked": True,
        },
    )
    revised = amendment(
        note, "1500", "270", details={"recipient_type": "UNREGISTERED", "recipient_gstin": None}
    )
    _, evidence = run([revised], originals={row["id"]: row for row in (invoice, note)})
    assert evidence["status"] == "DRAFT", evidence["issues"]
    assert evidence["form"]["9C_UNREG"]["taxable"] == "-500.00"
    assert evidence["form"]["10"]["taxable"] == "0.00"
    assert evidence["bridge"]["3.1a"]["igst"] == "-90.00"


def test_amended_advance_adjustment_has_positive_disclosure_and_negative_bridge():
    original = document(
        amount="500",
        igst="90",
        kind="ADVANCE_ADJUSTMENT",
        return_date="2026-08-01",
        document_date="2026-08-01",
    )
    revised = amendment(
        original,
        "600",
        "108",
        details={
            "items": [
                {
                    "goods_service": "SERVICES",
                    "taxable": "600",
                    "igst": "108",
                    "rate": "18",
                    "uqc": "NA",
                }
            ]
        },
    )
    _, evidence = run([revised], originals={original["id"]: original})
    assert evidence["form"]["11B_AMEND"]["taxable"] == "100.00"
    assert evidence["bridge"]["3.1a"]["igst"] == "-18.00"
    assert evidence["status"] == "DRAFT", evidence["issues"]


def test_increasing_a_credit_note_keeps_the_original_supply_financial_year_cutoff():
    invoice = document(return_date="2025-03-01", document_date="2025-03-01")
    note = document(
        amount="100",
        igst="18",
        kind="CREDIT_NOTE",
        document_number="CN-1",
        document_date="2026-09-01",
        return_date="2026-09-01",
        original_record_id=invoice["id"],
        details={"annual_return_checked": True},
    )
    revised = amendment(note, "120", "21.6")
    _, evidence = run([revised], originals={row["id"]: row for row in (invoice, note)})
    assert "NOTE_CUTOFF" in {row["code"] for row in evidence["issues"]}
    assert evidence["filing_cutoff"] == "2025-11-30"


def test_service_advance_adjustment_reduces_liability():
    advance = document(kind="ADVANCE", document_number="RCPT-1")
    adjustment = document(
        kind="ADVANCE_ADJUSTMENT", document_number="RCPT-2", amount="500", igst="90"
    )
    _, evidence = run([advance, adjustment])
    assert evidence["form"]["11A"]["igst"] == "180.00"
    assert evidence["form"]["11B"]["igst"] == "90.00"
    assert evidence["bridge"]["3.1a"]["igst"] == "90.00"
    assert evidence["table_counts"]["12_B2B"] == 0


def test_nil_requires_complete_outward_review_but_no_purchase_or_payment_test():
    _, evidence = run([])
    assert evidence["nil"] and evidence["status"] == "DRAFT"
    _, missing = calculate([], REG, START, END)
    assert not missing["nil"] and missing["status"] == "NEEDS_ATTENTION"


def test_turnover_profile_and_stale_coverage_are_reported():
    records = coverage([document()])
    _, evidence = calculate(records, REG | {"outward_profiles": []}, START, END, sequence=11)
    codes = {issue["code"] for issue in evidence["issues"]}
    assert "OUTWARD_PROFILE_MISSING" in codes and "COVERAGE_STALE_OUTWARD" in codes
    _, large = calculate(
        records,
        REG | {"outward_profiles": [REG["outward_profiles"][0] | {"annual_turnover": "50000001"}]},
        START,
        END,
    )
    assert "HSN_MISSING" in {issue["code"] for issue in large["issues"]}


def test_iff_invoice_not_repeated_but_quarter_bridge_includes_it():
    value = document(
        return_date="2026-10-01",
        details={
            "prior_filed_channel": "IFF",
            "prior_filing_reference": "Retained IFF ARN",
            "prior_filing_hash": "e" * 64,
            "prior_filing_date": "2026-11-10",
        },
    )
    _, evidence = calculate(coverage([value]), REG, START, dt.date(2026, 12, 31), sequence=10)
    assert evidence["iff_count"] == 1 and evidence["form"]["4A"]["igst"] == "0.00"
    assert evidence["bridge"]["3.1a"]["igst"] == "180.00"
    assert evidence["status"] == "DRAFT", evidence["issues"]


@pytest.mark.parametrize(
    ("kind", "filed", "amount", "expected"),
    [
        ("ADVANCE", "2026-11-10", "1000", "IFF_PERIOD"),
        ("INVOICE", "2026-10-15", "1000", "IFF_FILING_DATE"),
        ("INVOICE", "2026-11-10", "5000001", "IFF_VALUE_LIMIT"),
    ],
)
def test_ineligible_iff_evidence_cannot_suppress_ready_outward_tables(
    kind, filed, amount, expected
):
    value = document(
        amount=amount,
        igst="0",
        kind=kind,
        details={
            "prior_filed_channel": "IFF",
            "prior_filing_reference": "Actual prior IFF proof",
            "prior_filing_hash": "e" * 64,
            "prior_filing_date": filed,
        },
    )
    _, evidence = calculate(coverage([value]), REG, START, dt.date(2026, 12, 31), sequence=10)
    assert evidence["status"] == "NEEDS_ATTENTION"
    assert expected in {row["code"] for row in evidence["issues"]}


def test_completeness_uses_the_latest_source_sequence_not_the_latest_document_date():
    records = coverage([document()])
    newer = next(
        row
        for row in records
        if row["kind"] == "COVERAGE" and row["details"]["coverage_area"] == "OUTWARD"
    )
    stale = {
        **newer,
        "id": str(uuid.uuid4()),
        "return_date": "2026-10-31",
        "details": {**newer["details"], "covered_sequence": 9},
    }
    _, evidence = calculate([*records, stale], REG, START, END, sequence=10)
    assert evidence["status"] == "DRAFT", evidence["issues"]
    assert evidence["coverage_details"]["OUTWARD"]["record_id"] == newer["id"]


@pytest.mark.parametrize("current_conflict", [False, True])
def test_only_conflicting_proofs_at_the_current_source_cut_block_readiness(current_conflict):
    records = coverage([document()])
    base = next(
        row
        for row in records
        if row["kind"] == "COVERAGE" and row["details"]["coverage_area"] == "NOTES"
    )
    other = {
        **base,
        "id": str(uuid.uuid4()),
        "details": {
            **base["details"],
            "coverage_status": "NOT_APPLICABLE",
            "covered_sequence": 10 if current_conflict else 9,
        },
    }
    if not current_conflict:
        records.append(
            {**base, "id": str(uuid.uuid4()), "details": {**base["details"], "covered_sequence": 9}}
        )
    _, evidence = calculate([*records, other], REG, START, END, sequence=10)
    assert (
        "COVERAGE_CONFLICT_NOTES" in {row["code"] for row in evidence["issues"]}
    ) is current_conflict


def test_comparison_is_optional_but_differences_cannot_be_filed():
    _, evidence = run([document()], comparison={"form": {"3.1a": {"igst": "179.00"}}})
    assert evidence["status"] == "NEEDS_ATTENTION"
    assert evidence["reconciliation"][0]["difference"] == "1.00"


@pytest.mark.parametrize("rate", ["abc", "1e99999"])
def test_invalid_rate_returns_validation_error(rate):
    from reporting_contract.gst_outward import OutwardItem

    with pytest.raises(ValueError):
        OutwardItem(rate=rate)


def test_turnover_must_be_reviewed_for_the_current_gst_financial_year():
    outdated = REG | {
        "outward_profiles": [REG["outward_profiles"][0] | {"valid_from": "2025-04-01"}]
    }
    _, evidence = calculate(coverage([document()]), outdated, START, END)
    assert "OUTWARD_PROFILE_MISSING" in {issue["code"] for issue in evidence["issues"]}


def test_qrmp_is_not_valid_above_five_crore_turnover():
    high = REG | {
        "outward_profiles": [REG["outward_profiles"][0] | {"annual_turnover": "50000001"}]
    }
    _, evidence = calculate(coverage([]), high, START, dt.date(2026, 12, 31))
    assert "QRMP_TURNOVER" in {issue["code"] for issue in evidence["issues"]}


def test_credit_note_cutoff_and_annual_return_review_are_not_silently_assumed():
    original = document(document_date="2025-03-01", return_date="2025-03-01")
    note = document(kind="CREDIT_NOTE", document_number="CN-1", original_record_id=original["id"])
    _, evidence = run([note], originals={original["id"]: original})
    assert {"NOTE_CUTOFF", "NOTE_ANNUAL_REVIEW"} <= {issue["code"] for issue in evidence["issues"]}
