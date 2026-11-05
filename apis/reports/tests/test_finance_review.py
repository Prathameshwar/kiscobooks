import datetime as dt
import uuid

import pytest
from bank_evidence_fixture import evidence_dataset

from reports.domain.book_summaries import summarize
from reports.domain.statements import calculate
from reports.schemas.requests import RunRequest


@pytest.mark.parametrize("code,sign", [("PAYMENT_REGISTER", -1), ("RECEIPT_REGISTER", 1)])
def test_tender_reversals_net_to_zero(code, sign):
    rows = [
        {
            "journal_id": "original",
            "currency": "INR",
            "amount": "40.0000",
            "signed_amount": str(sign * 40),
        },
        {
            "journal_id": "reversal",
            "currency": "INR",
            "amount": "40.0000",
            "signed_amount": str(-sign * 40),
            "reversal_of_id": "original",
        },
    ]
    result = summarize(code, rows)
    assert result["amounts"]["INR"]["amount"] == "0.0000"
    assert result["voucher_count"] == 2


def test_unmatched_bank_worklist_excludes_completed_matches():
    facts, _, ids = evidence_dataset()
    query = RunRequest(
        code="BANK_RECONCILIATION_WORKLIST",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-30",
        account_id=ids["cash"],
        basis="TRANSACTION",
        currency="INR",
    )
    rows, _ = calculate(facts, query, dt.date(2026, 4, 1))
    assert all(row["status"] != "MATCHED" and row["residual"] != "0.0000" for row in rows)


def test_unmatched_bank_worklist_excludes_reversed_instruments(monkeypatch):
    import test_money_reports as existing

    captured = {}
    original = existing.calculate

    def capture(facts, query, coverage):
        captured.update(facts=facts, query=query, coverage=coverage)
        return original(facts, query, coverage)

    monkeypatch.setattr(existing, "calculate", capture)
    existing.test_reversed_bank_instrument_covers_original_and_reversal_without_replaying_cash()
    query = captured["query"].model_copy(
        update={
            "code": "BANK_RECONCILIATION_WORKLIST",
            "basis": "TRANSACTION",
            "currency": "INR",
            "statement_balance": None,
        }
    )
    rows, _ = calculate(captured["facts"], query, captured["coverage"])
    reversed_ids = {
        row.data["instrument_id"]
        for row in captured["facts"]
        if row.entity == "bank_instrument_event" and row.data["action"] == "REVERSED"
    }
    assert not any(row.get("instrument_id") in reversed_ids for row in rows)


def test_wide_pdf_repeats_invoice_identity_on_every_band(tmp_path):
    import json
    from dataclasses import asdict

    from pypdf import PdfReader
    from test_presentation_rendering import document

    from reports.rendering.pdf_layout import render
    from reports.tasks.report_catalog import catalog

    columns = catalog().resolve("SALES_REGISTER").definition.views[0].columns
    rows = [
        {
            "bill_reference": "INV-UNIQUE-A",
            "account_name": "Customer Alpha",
            "period": "CURRENT",
            "currency": "INR",
            "payable": "118.0000",
        }
    ]
    pdf = tmp_path / "wide.pdf"
    render(
        [json.dumps(row) for row in rows],
        pdf,
        {
            "document": document().wire(),
            "columns": [asdict(column) for column in columns],
            "rows": 100,
            "cells": 10000,
            "pages": 20,
        },
    )
    pages = [page.extract_text() for page in PdfReader(pdf).pages]
    assert len(pages) > 1
    assert all("INV-UNIQUE-A" in page for page in pages)


def test_as_of_finance_contracts_do_not_request_a_from_date():
    from reports.tasks.report_catalog import catalog

    for code in ("BANK_RECONCILIATION", "INVOICE_SETTLEMENT_REGISTER"):
        properties = catalog().resolve(code).handler.parameters()["properties"]
        assert "date_to" in properties
        assert "date_from" not in properties


def test_income_and_expenditure_hides_unused_accounts_unless_requested():
    from financial_fixture import financial_dataset

    from reports.tasks.report_catalog import catalog

    facts, _ = financial_dataset()
    adapter = catalog().resolve("INCOME_EXPENSE").handler
    assert adapter.parameters()["properties"]["show_zero"]["default"] is False
    query = RunRequest(
        code="INCOME_EXPENSE",
        generation_id=uuid.uuid4(),
        date_from="2026-04-01",
        date_to="2026-04-01",
    )
    rows, _ = calculate(facts, query, dt.date(2026, 4, 1))
    included, _ = calculate(
        facts, query.model_copy(update={"show_zero": True}), dt.date(2026, 4, 1)
    )
    assert not any(row.get("account_id") and row["amount"] == "0.0000" for row in rows)
    assert len(included) > len(rows)


@pytest.mark.parametrize("code", ["PROFIT_LOSS", "INCOME_EXPENSE"])
def test_fiscal_year_selection_includes_eligible_imported_ytd(code):
    from test_opening_migration_modes import ytd_dataset

    from reports.tasks.report_catalog import catalog

    facts, _ = ytd_dataset()
    query = (
        catalog()
        .resolve(code)
        .handler.request(
            uuid.uuid4(), {"date_from": "2026-04-01", "date_to": "2026-04-30"}, dt.date(2026, 4, 2)
        )
    )
    rows, evidence = calculate(facts, query, dt.date(2026, 4, 2))
    assert rows[-1]["amount"] == "260.0000"
    assert evidence["imported_ytd_included"] is True


async def test_versioned_source_exposes_its_immutable_verification_time(app, client):
    from conftest import COMPANY, headers
    from test_source_versions import staged

    identities, _ = await staged(app)
    response = await client.get(
        f"/v2/companies/{COMPANY}/report-generations/{identities[2]}", headers=headers()
    )
    assert response.status_code == 200, response.text
    verified = response.json()["verified_at"]
    assert verified is not None
    dt.datetime.fromisoformat(verified)
    again = await client.get(
        f"/v2/companies/{COMPANY}/report-generations/{identities[2]}", headers=headers()
    )
    assert again.json()["verified_at"] == verified
