"""Tax workspaces keep source grains, signs and currency totals exact."""

import datetime as dt
import uuid

import pytest
from test_invoice_reports import purchase_dataset, tax_dataset

from reports.domain.statements import calculate
from reports.schemas.requests import RunRequest


def credit_history_dataset():
    from fixtures import source

    facts, ids, _, _, _, component = purchase_dataset()
    action_id = uuid.uuid4()
    facts.extend(
        [
            source(
                "invoice_credit_action",
                action_id,
                {
                    "invoice_id": ids["invoice"],
                    "component_id": str(component),
                    "expected_event_id": str(uuid.uuid4()),
                    "kind": "VERIFY",
                    "amount": "20",
                    "event_date": "2026-04-03",
                    "posting_date": "2026-05-02",
                    "currency": "INR",
                    "journal_id": None,
                    "offset_account_id": None,
                    "cash_deposit_line_id": None,
                    "annual_return_filed_on": None,
                    "document_verified": True,
                    "supply_received": True,
                    "business_use": True,
                    "restrictions_checked": True,
                    "supplier_report_matched": True,
                    "tax_payment_verified": True,
                    "return_filed": True,
                    "supplier_paid": True,
                    "reference": "verified supplier evidence",
                    "evidence_sha256": "a" * 64,
                    "reason": "Verified committed evidence",
                },
            ),
            source(
                "invoice_credit_event",
                uuid.uuid4(),
                {"invoice_id": ids["invoice"], "action_id": str(action_id)},
            ),
        ]
    )
    return facts


def test_credit_late_posted_evidence_does_not_backdate_eligibility():
    facts = credit_history_dataset()
    query = RunRequest(
        code="INVOICE_CREDIT_REGISTER",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-30",
    )
    rows, _ = calculate(facts, query, dt.date(2026, 4, 1))
    assert rows[0]["pending"] == "20.0000"
    rows, _ = calculate(
        facts,
        query.model_copy(
            update={"date_from": dt.date(2026, 6, 1), "date_to": dt.date(2026, 6, 30)}
        ),
        dt.date(2026, 4, 1),
    )
    assert len(rows) == 1 and rows[0]["eligible_unclaimed"] == "20.0000"


def test_tax_register_exposes_business_facts_and_full_result_totals():
    facts, *_ = tax_dataset()
    query = RunRequest(
        code="INVOICE_TAX_REGISTER",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-30",
    )
    rows, evidence = calculate(facts, query, dt.date(2026, 4, 1))
    assert rows[0]["taxable_value"] == "200"
    assert rows[0]["direction"] == "ORIGINAL"
    assert evidence["tax_summary"]["amounts"]["INR"]["tax_amount"] == "20.0000"


def test_tax_component_summary_deduplicates_supply_bases_and_keeps_currency_and_returns():
    from reports.domain.tax_summaries import summarize

    rows = [
        {
            "row_kind": "TAX_COMPONENT",
            "invoice_id": "sale",
            "supply_id": "supply",
            "component_id": code,
            "invoice_kind": "SALES",
            "currency": "INR",
            "taxable_value": "100",
            "tax_amount": "9",
            "tax_code": code,
        }
        for code in ("CGST", "SGST")
    ]
    rows += [
        rows[0]
        | {
            "invoice_id": "note",
            "supply_id": "return",
            "component_id": "return",
            "invoice_kind": "CREDIT_NOTE",
            "taxable_value": "25",
            "tax_amount": "4.5",
        },
        rows[0]
        | {
            "invoice_id": "foreign",
            "supply_id": "usd",
            "component_id": "usd",
            "currency": "USD",
            "taxable_value": "50",
            "tax_amount": "5",
        },
        rows[0] | {"period": "COMPARATIVE"},
    ]
    summary = summarize("INVOICE_TAX_REGISTER", rows)
    assert summary["amounts"]["INR"]["taxable_value"] == "75.0000"
    assert summary["amounts"]["INR"]["tax_amount"] == "13.5000"
    assert summary["amounts"]["USD"]["tax_amount"] == "5.0000"
    assert summary["component_count"] == 4


@pytest.mark.parametrize("search,count", [("INV-1", 1), ("missing voucher", 0)])
def test_tax_search_precedes_full_result_totals(search, count):
    facts, *_ = tax_dataset()
    query = RunRequest(
        code="INVOICE_TAX_REGISTER",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-30",
        search=search,
    )
    rows, evidence = calculate(facts, query, dt.date(2026, 4, 1))
    assert len(rows) == count
    assert evidence["tax_summary"]["component_count"] == count


def test_credit_summary_uses_positions_without_counting_event_amounts_twice():
    from reports.domain.tax_summaries import summarize

    rows = [
        {
            "row_kind": "CREDIT_POSITION",
            "invoice_id": "purchase",
            "component_id": "tax",
            "currency": "INR",
            "recorded_tax": "20",
            "pending": "0",
            "eligible_unclaimed": "10",
            "claimed": "7",
            "suspended": "3",
            "blocked": "0",
            "rcm_discharged": "5",
        },
        {
            "row_kind": "CREDIT_EVENT",
            "invoice_id": "purchase",
            "currency": "INR",
            "action": "VERIFY",
            "event_amount": "20",
        },
        {
            "row_kind": "CREDIT_EVENT",
            "invoice_id": "purchase",
            "currency": "INR",
            "action": "CLAIM",
            "event_amount": "10",
        },
    ]
    summary = summarize("INVOICE_CREDIT_REGISTER", rows)
    assert summary["position_count"] == 1 and summary["event_count"] == 2
    assert summary["amounts"]["INR"]["recorded_tax"] == "20.0000"
    assert summary["amounts"]["INR"]["claimed"] == "7.0000"
    assert summary["event_amounts"]["INR"]["VERIFY"] == "20.0000"


def test_credit_positions_expose_tax_code_and_search_entire_selected_history():
    facts, *_ = purchase_dataset()
    query = RunRequest(
        code="INVOICE_CREDIT_REGISTER",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-30",
        search="IGST",
    )
    rows, evidence = calculate(facts, query, dt.date(2026, 4, 1))
    assert rows[0]["tax_code"] == "IGST"
    assert evidence["tax_summary"]["amounts"]["INR"]["pending"] == "20.0000"
    assert (
        calculate(facts, query.model_copy(update={"search": "missing tax"}), dt.date(2026, 4, 1))[0]
        == []
    )


def test_tax_bridge_reports_verified_movement_not_a_false_mismatch():
    facts, *_ = tax_dataset()
    query = RunRequest(
        code="TAX_GL_BRIDGE",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-30",
    )
    rows, evidence = calculate(facts, query, dt.date(2026, 4, 1))
    assert len(rows) == 1 and rows[0]["account_name"] == "Output IGST"
    summary = evidence["tax_summary"]
    assert summary["ledger_count"] == 1 and summary["invoice_count"] == 1
    assert summary["amounts"]["INR"] == {"debit": "0.0000", "credit": "20.0000", "net": "-20.0000"}
    assert summary["verification"] == "VERIFIED_SOURCE_LINEAGE"
    assert "mismatch" not in summary
    assert not calculate(
        facts, query.model_copy(update={"search": "missing ledger"}), dt.date(2026, 4, 1)
    )[0]
    assert (
        len(
            calculate(
                facts, query.model_copy(update={"search": "output igst"}), dt.date(2026, 4, 1)
            )[0]
        )
        == 1
    )


def test_tax_bridge_ledger_purpose_and_date_filters_use_posted_line_grain():
    facts, *_ = tax_dataset()
    ledger = next(
        row.source_id
        for row in facts
        if row.entity == "account" and row.data["code"] == "OUTPUT_IGST"
    )
    query = RunRequest(
        code="TAX_GL_BRIDGE",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-01",
        tax_ledger_id=ledger,
        tax_purpose="OUTPUT_IGST",
        tax_code="IGST",
    )
    assert not calculate(facts, query, dt.date(2026, 4, 1))[0]
    assert (
        len(
            calculate(
                facts, query.model_copy(update={"date_basis": "TAX_POINT"}), dt.date(2026, 4, 1)
            )[0]
        )
        == 1
    )
    matching = query.model_copy(update={"date_to": dt.date(2026, 4, 30)})
    assert len(calculate(facts, matching, dt.date(2026, 4, 1))[0]) == 1
    other_ledger = next(
        row.source_id
        for row in facts
        if row.entity == "account" and row.data["code"] != "OUTPUT_IGST"
    )
    for filter_value in (
        {"tax_ledger_id": other_ledger},
        {"tax_purpose": "CLAIM"},
        {"tax_code": "SGST"},
    ):
        assert not calculate(facts, matching.model_copy(update=filter_value), dt.date(2026, 4, 1))[
            0
        ]


def test_tax_bridge_summary_keeps_currency_and_comparative_evidence_separate():
    from reports.domain.tax_summaries import summarize

    rows = [
        {
            "row_kind": "GL_ENTRY",
            "invoice_id": "a",
            "currency": "INR",
            "side": "DEBIT",
            "amount": "30",
        },
        {
            "row_kind": "GL_ENTRY",
            "invoice_id": "a",
            "currency": "INR",
            "side": "CREDIT",
            "amount": "10",
        },
        {
            "row_kind": "GL_ENTRY",
            "invoice_id": "b",
            "currency": "USD",
            "side": "CREDIT",
            "amount": "2",
        },
    ]
    summary = summarize("TAX_GL_BRIDGE", [*rows, rows[0] | {"period": "COMPARATIVE"}])
    assert summary["ledger_count"] == 3 and summary["invoice_count"] == 2
    assert summary["comparison_present"] is True
    assert summary["amounts"]["INR"]["net"] == "20.0000"
    assert summary["amounts"]["USD"]["net"] == "-2.0000"


def test_tax_ledger_filter_is_rejected_for_non_bridge_reports():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RunRequest(
            code="INVOICE_TAX_REGISTER",
            generation_id=uuid.uuid4(),
            date_from="2026-04-01",
            date_to="2026-04-30",
            tax_ledger_id=uuid.uuid4(),
        )


def test_tax_ledger_filter_must_belong_to_the_frozen_company_source():
    from billing_platform.errors import ValidationFailedError

    facts, *_ = tax_dataset()
    query = RunRequest(
        code="TAX_GL_BRIDGE",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-30",
        tax_ledger_id=uuid.uuid4(),
    )
    with pytest.raises(ValidationFailedError, match="outside the frozen company source"):
        calculate(facts, query, dt.date(2026, 4, 1))


@pytest.mark.parametrize(
    "code", ["INVOICE_TAX_REGISTER", "INVOICE_CREDIT_REGISTER", "TAX_GL_BRIDGE"]
)
def test_tax_default_print_views_emphasize_business_columns(code):
    from reports.tasks.report_catalog import catalog

    views = catalog().resolve(code).definition.views
    default = next(view for view in views if view.key == "default")
    assert len(default.columns) <= 11
    assert any(column.key == "period" for column in default.columns)
    assert all(not column.key.endswith("_id") for column in default.columns)
    assert any(
        column.kind == "IDENTIFIER"
        for view in views
        if view.key != "default"
        for column in view.columns
    )


@pytest.mark.parametrize(
    "mode,key,label",
    [
        ("EVENTS", "RCM_DISCHARGE", "RCM Discharge"),
        ("POSITIONS", "rcm_discharged", "RCM Discharged"),
    ],
)
def test_tax_export_metadata_preserves_rcm_acronym(mode, key, label):
    import json
    from pathlib import Path

    from billing_platform.display import DisplayConfiguration

    from reports.rendering.tax import metadata

    summary = {
        "code": "INVOICE_CREDIT_REGISTER",
        "mode": mode,
        "amounts": {"INR": {key: "20.0000"}},
        "event_amounts": {"INR": {key: "20.0000"}},
    }
    fixture = json.loads(
        (Path(__file__).parents[3] / "libs/platform/tests/fixtures/report-display.json").read_text(
            "utf-8"
        )
    )
    values = dict(
        metadata(
            {"tax_summary": summary},
            {"date_from": "2026-04-01", "date_to": "2026-04-30"},
            DisplayConfiguration(**fixture["config"]),
        )
    )
    assert values["INR"] == label + " 20.00"
