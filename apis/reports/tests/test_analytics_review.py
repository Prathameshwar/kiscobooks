from analytics_fixture import VALUES, document, stock_for
from test_analytics_profit import financial

from reports.domain.analytics_profit import calculate
from reports.domain.reporting.drilldowns import parameters_for
from reports.schemas.analytics import CashParameters, ExpenseParameters


def test_duplicate_common_line_does_not_assign_the_same_cost_twice():
    sale = document()
    stock, _ = stock_for(sale)
    line = sale["supplies"][0]
    sale["supplies"] = [line | {"commercial": "500"}, line | {"id": "another", "commercial": "500"}]
    rows, _ = calculate(financial(), [], [sale], VALUES, stock, "INR", view="products")
    assert rows[0]["net_sales"] == "1000.0000"
    assert rows[0]["cost"] is None and rows[0]["gross_profit"] is None


def test_expense_and_cash_specific_thresholds_validate_without_leaking_extra_fields():
    assert ExpenseParameters.model_validate(VALUES).material_amount == "1000"
    assert CashParameters.model_validate(VALUES).due_within_days == 30
    assert ExpenseParameters.model_validate(VALUES | {"search": "  rent  "}).search == "rent"


def test_comparative_drilldowns_use_the_row_period_and_invoice_currency():
    values = VALUES | {"comparative_from": "2026-03-01", "comparative_to": "2026-03-31"}
    identity = "01990000-0000-7000-8000-000000000099"
    row = {
        "period": "COMPARATIVE",
        "party_id": identity,
        "account_id": identity,
        "currency": "INR",
        "document_currency": "USD",
    }
    sales = parameters_for("analytics_sales", values, row, "2026-01-01")
    assert sales["date_from"] == "2026-03-01" and sales["currency"] == "USD"
    ledger = parameters_for("account_entries", values, row, "2026-01-01")
    assert ledger["date_to"] == "2026-03-31"
