from analytics_fixture import VALUES, document, stock_for

from reports.domain.analytics_cash import calculate, tied_stock
from reports.domain.analytics_common import stock_index


def inputs():
    return {
        "accounts": {"cash": {"name": "Cash"}, "bank": {"name": "Bank"}},
        "periods": {
            "CURRENT": {
                "lines": [
                    {
                        "account_id": "cash",
                        "posting_date": "2026-03-31",
                        "side": "DEBIT",
                        "base_amount": "1000",
                        "opening_effect": False,
                    },
                    {
                        "account_id": "cash",
                        "posting_date": "2026-04-02",
                        "side": "CREDIT",
                        "base_amount": "300",
                        "opening_effect": False,
                    },
                    {
                        "account_id": "bank",
                        "posting_date": "2026-04-02",
                        "side": "DEBIT",
                        "base_amount": "300",
                        "opening_effect": False,
                    },
                    {
                        "account_id": "bank",
                        "posting_date": "2026-04-05",
                        "side": "DEBIT",
                        "base_amount": "500",
                        "opening_effect": False,
                    },
                ],
                "movements": [
                    {
                        "journal_id": "transfer",
                        "date": "2026-04-02",
                        "amount": "0",
                        "label": "Transfer",
                    },
                    {
                        "journal_id": "receipt",
                        "date": "2026-04-05",
                        "amount": "500",
                        "label": "Receipt",
                    },
                ],
                "bills": [],
            }
        },
    }


def test_internal_cash_bank_transfers_do_not_inflate_receipts_or_payments():
    rows, evidence = calculate(inputs(), VALUES, stock_index([]), "INR")
    metrics = evidence["analytics"]["amounts"]["CURRENT"]["INR"]
    assert metrics["cash_receipts"] == "500.0000" and metrics["cash_payments"] == "0.0000"
    assert metrics["closing_cash"] == "1500.0000" and metrics["cash_adjustments"] == "0.0000"
    assert sum(float(row["closing"]) for row in rows) == 1500


def test_unapplied_credits_do_not_reduce_overdue_receivables_and_unknown_due_dates_stay_unknown():
    data = inputs()
    common = {
        "account_name": "Buyer",
        "currency": "USD",
        "role": "CUSTOMER",
        "due_date": "2026-04-10",
        "days_overdue": 20,
    }
    data["periods"]["CURRENT"]["bills"] = [
        common | {"direction": "DEBT", "report_amount": "1000"},
        common | {"direction": "CREDIT", "report_amount": "300"},
        common | {"direction": "DEBT", "report_amount": "200", "due_date": None},
    ]
    rows, evidence = calculate(data, VALUES, stock_index([]), "INR", view="customers")
    metrics = evidence["analytics"]["amounts"]["CURRENT"]["INR"]
    assert metrics["overdue_receivables"] == "1000.0000"
    assert metrics["receivables"] == "1200.0000"
    assert len(rows) == 3 and rows[0]["currency"] == "INR" and rows[0]["document_currency"] == "USD"


def test_inventory_value_is_unavailable_when_snapshot_date_differs():
    stock, _ = stock_for(document())
    assert tied_stock(stock, "2026-04-29", 90) == ([], None)
    rows, evidence = calculate(inputs(), VALUES, stock_index([]), "INR", view="stock")
    assert not rows and evidence["analytics"]["amounts"]["CURRENT"]["INR"]["stock_tied_up"] is None


def test_supplier_dues_include_overdue_and_horizon_but_not_later_or_unknown():
    data = inputs()
    common = {
        "account_name": "Supplier",
        "currency": "INR",
        "role": "SUPPLIER",
        "direction": "DEBT",
        "report_amount": "100",
    }
    data["periods"]["CURRENT"]["bills"] = [
        common | {"due_date": day} for day in ("2026-04-15", "2026-05-10", "2026-06-01", None)
    ]
    rows, evidence = calculate(data, VALUES, stock_index([]), "INR", view="suppliers")
    assert len(rows) == 4
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["supplier_dues"] == "200.0000"


def test_search_limits_rows_without_misrepresenting_company_totals_and_movements():
    rows, evidence = calculate(inputs(), VALUES | {"search": "bank"}, stock_index([]), "INR")
    assert len(rows) == 1 and rows[0]["label"] == "Bank"
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["closing_cash"] == "1500.0000"
    rows, _ = calculate(inputs(), VALUES, stock_index([]), "INR", view="movements")
    assert rows[0]["movement_kind"] == "INTERNAL_TRANSFER"
