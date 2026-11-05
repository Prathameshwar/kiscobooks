import datetime as dt
import uuid
from copy import deepcopy

import pytest
from billing_platform.errors import ConflictError
from pydantic import ValidationError

from reports.domain.reporting.balance_views import present
from reports.tasks.report_catalog import catalog


def period(name="CURRENT", amount="100.0000"):
    return (
        [
            {
                "period": name,
                "row_kind": "ACCOUNT",
                "account_id": nature,
                "account_code": nature,
                "account_name": nature,
                "group_id": nature,
                "group_code": nature,
                "group_name": nature,
                "nature": nature,
                "amount": amount if nature == "ASSET" else "0.0000",
                "currency": "INR",
            }
            for nature in ("ASSET", "LIABILITY", "EQUITY")
        ]
        + [
            {
                "period": name,
                "row_kind": kind,
                "amount": amount if kind == "CURRENT_YEAR_EARNINGS" else "0.0000",
                "currency": "INR",
            }
            for kind in (
                "OPENING_EARNINGS",
                "PRIOR_UNTRANSFERRED_EARNINGS",
                "CURRENT_YEAR_EARNINGS",
            )
        ]
        + [
            {
                "period": name,
                "row_kind": "BALANCE_SHEET_CONTROL",
                "assets": amount,
                "liabilities": "0.0000",
                "equity": "0.0000",
                "untransferred_earnings": amount,
                "difference": "0.0000",
            }
        ]
    )


def test_totals_include_earnings_once_and_hide_zero_accounts():
    rows, summary = present(period(), comparison=False, show_zero=False)
    assert summary["totals"]["EQUITY"]["current"] == "100.0000"
    assert summary["totals"]["LIABILITIES_EQUITY"]["current"] == "100.0000"
    assert summary["difference"]["current"] == "0.0000"
    assert [r["account_id"] for r in rows if r["row_kind"] == "ACCOUNT"] == ["ASSET"]
    assert len([r for r in rows if r["row_kind"] == "EARNINGS"]) == 3


def test_comparison_and_losses_preserve_exact_signs():
    rows, summary = present(
        period(amount="-50.0000") + period("COMPARATIVE"), comparison=True, show_zero=False
    )
    account = next(r for r in rows if r.get("account_id") == "ASSET")
    assert account["change_amount"] == "-150.0000"
    assert account["change_percent"] == "-150.00%"
    assert summary["totals"]["EQUITY"]["current"] == "-50.0000"


@pytest.mark.parametrize(
    "mutation", ["total", "earnings", "duplicate", "unknown", "currency", "amount"]
)
def test_invalid_source_cannot_publish(mutation):
    source = deepcopy(period())
    if mutation == "total":
        source[-1]["assets"] = "99.0000"
    elif mutation == "earnings":
        source[-2]["amount"] = "99.0000"
    elif mutation == "duplicate":
        source.append(source[0])
    elif mutation == "unknown":
        source[0]["nature"] = "INCOME"
    elif mutation == "currency":
        source[0]["currency"] = "USD"
    else:
        source[0]["amount"] = "NaN"
    with pytest.raises(ConflictError):
        present(source, comparison=False, show_zero=False)


def test_missing_period_and_classification_change_rejected():
    with pytest.raises(ConflictError):
        present(period(), comparison=True, show_zero=False)
    prior = period("COMPARATIVE")
    prior[0]["group_name"] = "Changed"
    with pytest.raises(ConflictError):
        present(period() + prior, comparison=True, show_zero=False)


def test_zero_current_retains_prior_account_and_zero_percentage_is_undefined():
    rows, _ = present(
        period(amount="0.0000") + period("COMPARATIVE"), comparison=True, show_zero=False
    )
    assert any(r.get("account_id") == "ASSET" for r in rows)
    rows, _ = present(period() + period("COMPARATIVE", "0.0000"), comparison=True, show_zero=True)
    assert next(r for r in rows if r.get("account_id") == "ASSET")["change_percent"] is None


def test_as_of_adapter_uses_retained_history_and_rejects_unavailable_dates():
    handler = catalog().resolve("BALANCE_SHEET", 6).handler
    query = handler.request(
        uuid.uuid4(), {"date_to": "2027-03-31", "comparative_to": "2026-04-30"}, dt.date(2026, 4, 1)
    )
    assert query.date_from == query.comparative_from == dt.date(2026, 4, 1)
    assert query.date_to == dt.date(2027, 3, 31)
    with pytest.raises(ValidationError):
        handler.request(
            uuid.uuid4(),
            {"date_to": "2027-03-31", "comparative_to": "2026-03-31"},
            dt.date(2026, 4, 1),
        )
