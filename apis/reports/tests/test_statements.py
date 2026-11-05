import datetime as dt
import uuid
from decimal import Decimal

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError
from financial_fixture import financial_dataset, financial_manifest
from fixtures import source
from pydantic import ValidationError

from reports.domain.reconcile import reconcile
from reports.domain.statements import calculate
from reports.schemas.requests import RunRequest


def report(code, **changes):
    rows, ids = financial_dataset()
    query = RunRequest.model_validate(
        {
            "code": code,
            "generation_id": str(uuid.uuid4()),
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
        }
        | changes
    )
    reconcile(rows, financial_manifest(rows).control)
    return calculate(rows, query, dt.date(2026, 4, 1))[0], ids


def test_trial_balance_cash_book_profit_and_earnings_reconcile_across_years():
    rows, _ = report("TRIAL_BALANCE")
    assert rows[-1]["difference"] == "0.0000"
    assert sum(Decimal(row.get("closing", "0")) for row in rows) == 0
    cash, _ = report("CASH_BOOK")
    assert [row["balance"] for row in cash] == ["0.0000", "100.0000", "220.0000", "180.0000"]
    profit, _ = report("PROFIT_LOSS")
    assert profit[-1]["amount"] == "160.0000"
    balance, _ = report("BALANCE_SHEET", date_from="2027-04-01", date_to="2027-04-30")
    assert (
        next(row["amount"] for row in balance if row["row_kind"] == "PRIOR_UNTRANSFERRED_EARNINGS")
        == "160.0000"
    )
    assert (
        next(row["amount"] for row in balance if row["row_kind"] == "CURRENT_YEAR_EARNINGS")
        == "0.0000"
    )
    assert balance[-1]["assets"] == "260.0000" and balance[-1]["equity"] == "100.0000"
    assert balance[-1]["difference"] == "0.0000"


def test_reversed_initial_opening_stays_out_of_operating_profit() -> None:
    rows, ids = financial_dataset()
    opening = next(row for row in rows if row.entity == "journal" and row.data["kind"] == "OPENING")
    original_credit = next(
        row
        for row in rows
        if row.entity == "journal_line"
        and row.data["journal_id"] == str(opening.source_id)
        and row.data["side"] == "CREDIT"
    )
    rows = [
        source("journal_line", row.source_id, row.data | {"account_id": ids["income"]})
        if row.source_id == original_credit.source_id and row.entity == "journal_line"
        else row
        for row in rows
    ]
    for kind, credit, debit, original_id in (
        ("REVERSAL", "cash", "income", str(opening.source_id)),
        ("OPENING", "equity", "cash", None),
    ):
        journal_id = uuid.uuid4()
        rows.append(
            source(
                "journal",
                journal_id,
                opening.data
                | {
                    "kind": kind,
                    "number": str(journal_id),
                    "source_id": str(journal_id),
                    "reversal_of_id": original_id,
                },
            )
        )
        for sequence, (side, account) in enumerate((("DEBIT", debit), ("CREDIT", credit)), 1):
            rows.append(
                source(
                    "journal_line",
                    uuid.uuid4(),
                    original_credit.data
                    | {
                        "journal_id": str(journal_id),
                        "sequence": sequence,
                        "side": side,
                        "account_id": ids[account],
                    },
                )
            )
    reconcile(rows, financial_manifest(rows).control)
    query = {
        "generation_id": str(uuid.uuid4()),
        "date_from": "2026-04-01",
        "date_to": "2026-04-30",
    }

    def result(code: str) -> list[dict[str, object]]:
        request = RunRequest.model_validate(query | {"code": code})
        return calculate(rows, request, dt.date(2026, 4, 1))[0]

    trial = result("TRIAL_BALANCE")
    cash = next(row for row in trial if row.get("account_id") == ids["cash"])
    assert cash["opening"] == "100.0000" and cash["closing"] == "180.0000"
    profit = result("PROFIT_LOSS")
    assert profit[-1]["amount"] == "160.0000"
    balance = result("BALANCE_SHEET")
    assert balance[-1]["difference"] == "0.0000"


def test_aging_advances_and_new_year_allocation_keep_original_due_date():
    bills, _ = report("OUTSTANDING_BILLS")
    invoice = next(row for row in bills if row["direction"] == "DEBT")
    assert invoice["remaining"] == "150.0000" and invoice["due_date"] == "2026-04-02"
    aged, _ = report("AGING")
    assert aged[0]["debt"] == "150.0000" and aged[0]["unapplied_credit"] == "70.0000"
    assert aged[0]["DAYS_1_30"] == "150.0000"
    advances, _ = report("ADVANCES")
    assert len(advances) == 1 and advances[0]["remaining"] == "70.0000"
    next_year, _ = report("OUTSTANDING_BILLS", date_from="2027-04-01", date_to="2027-04-30")
    invoice = next(row for row in next_year if row["direction"] == "DEBT")
    assert invoice["remaining"] == "120.0000" and invoice["due_date"] == "2026-04-02"
    assert invoice["aging_bucket"] == "DAYS_OVER_90"


def test_comparatives_and_exact_monthly_gross_turnover():
    rows, _ = report(
        "PROFIT_LOSS",
        date_from="2027-04-01",
        date_to="2027-04-30",
        comparative_from="2026-04-01",
        comparative_to="2026-04-30",
    )
    profits = {row["period"]: row["amount"] for row in rows if row["row_kind"] == "NET_PROFIT"}
    assert profits == {"CURRENT": "0.0000", "COMPARATIVE": "160.0000"}
    summary, ids = report("ACCOUNT_SUMMARY", grain="MONTH")
    cash = next(row for row in summary if row["account_id"] == ids["cash"])
    assert cash["opening"] == "100.0000"
    assert cash["debit"] == "120.0000" and cash["credit"] == "40.0000"
    assert cash["date"] == "2026-04-01"


def test_reporting_rejects_missing_history_and_wrong_currency_or_object():
    with pytest.raises(ConflictError):
        report("ACCOUNT_LEDGER", date_from="2026-03-01")
    with pytest.raises(ValidationError):
        report("ACCOUNT_LEDGER", currency="USD")
    with pytest.raises(ValidationFailedError):
        report("ACCOUNT_LEDGER", account_id=str(uuid.uuid4()))


def test_day_book_has_only_entries_and_aging_uses_selected_amount_basis():
    from reports.domain.registers import aging

    rows, _ = report("DAY_BOOK")
    assert all(row["row_kind"] == "ENTRY" for row in rows)
    rows = aging(
        [
            {
                "party_id": "p",
                "role": "CUSTOMER",
                "account_id": "a",
                "currency": "USD",
                "report_currency": "INR",
                "remaining": "2.0000",
                "report_amount": "166.0000",
                "direction": "DEBT",
                "aging_bucket": "CURRENT",
            }
        ]
    )
    assert rows[0]["currency"] == "INR" and rows[0]["debt"] == "166.0000"


def test_monthly_account_and_group_summaries_keep_cross_year_carry():
    rows, ids = report(
        "ACCOUNT_SUMMARY", grain="MONTH", date_from="2027-04-01", date_to="2027-04-30"
    )
    cash = next(row for row in rows if row.get("account_id") == ids["cash"])
    group = next(
        row
        for row in rows
        if row["row_kind"] == "GROUP_PERIOD" and row["group_id"] == cash["group_id"]
    )
    for row in (cash, group):
        assert row["opening"] == "180.0000"
        assert row["debit"] == "30.0000" and row["credit"] == "0.0000"
        assert row["closing"] == "210.0000"


@pytest.mark.parametrize(
    "grain,dates", [("MONTH", ["2026-06-01"]), ("DAY", ["2026-06-05", "2026-06-06"])]
)
def test_quiet_periods_keep_account_and_group_balances(grain, dates):
    facts, ids = financial_dataset()
    query = RunRequest.model_validate(
        {
            "code": "ACCOUNT_SUMMARY",
            "generation_id": uuid.uuid4(),
            "date_from": "2026-06-05",
            "date_to": "2026-06-06",
            "account_id": ids["cash"],
            "grain": grain,
        }
    )
    rows, _ = calculate(facts, query, dt.date(2026, 4, 1))
    for kind in ("ACCOUNT_PERIOD", "GROUP_PERIOD"):
        periods = [row for row in rows if row["row_kind"] == kind]
        assert [row["date"] for row in periods] == dates
        assert all(row["opening"] == row["closing"] == "180.0000" for row in periods)
        assert all(row["debit"] == row["credit"] == "0.0000" for row in periods)


def test_quiet_months_between_movements_keep_the_prefix():
    rows, ids = report("ACCOUNT_SUMMARY", grain="MONTH", date_to="2027-04-30")
    cash = [row for row in rows if row.get("account_id") == ids["cash"]]
    assert len(cash) == 13
    assert all(row["opening"] == row["closing"] == "180.0000" for row in cash[1:-1])
    assert cash[-1]["closing"] == "210.0000"


def test_summary_expansion_is_bounded_before_allocating_rows():
    with pytest.raises(ConflictError, match="bound"):
        report("ACCOUNT_SUMMARY", date_to="9999-12-31")
