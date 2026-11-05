from decimal import Decimal

import pytest
from analytics_fixture import VALUES, document, stock_for
from test_analytics_cash import inputs
from test_analytics_profit import financial

from reports.domain.analytics_cash import calculate as cash
from reports.domain.analytics_common import stock_index
from reports.domain.analytics_customers import calculate as customers
from reports.domain.analytics_expenses import calculate as expenses
from reports.domain.analytics_profit import calculate as profit
from reports.domain.analytics_sales import calculate as sales


def test_product_search_finds_stock_names_without_changing_company_sales_totals():
    sale = document()
    stock, _ = stock_for(sale)
    name = next(
        item["name"]
        for item in stock["items"].values()
        if item["item_id"]
        == next(m["item_id"] for m in stock["movements"] if m["action"] == "SALE")
    )
    rows, evidence = sales([sale], VALUES | {"search": name}, stock, view="products")
    assert len(rows) == 1 and rows[0]["net_sales"] == "1000.0000"
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["net_sales"] == "1000.0000"


def test_profit_product_search_finds_item_names_and_retains_exact_cost_evidence():
    sale = document()
    stock, _ = stock_for(sale)
    name = stock["items"][next(m["item_id"] for m in stock["movements"] if m["action"] == "SALE")][
        "name"
    ]
    rows, _ = profit(
        financial(), [], [sale], VALUES | {"search": name}, stock, "INR", view="products"
    )
    assert len(rows) == 1 and rows[0]["cost"] == "400.0000"


def test_category_search_matches_the_displayed_supply_category():
    rows, _ = sales([document()], VALUES | {"search": "GOODS"}, stock_index([]), view="categories")
    assert len(rows) == 1 and rows[0]["net_sales"] == "1000.0000"


def test_customer_returns_without_retained_purchases_remain_in_activity_and_totals():
    returned = document("200", kind="CREDIT_NOTE")
    rows, evidence = customers([returned], VALUES, "2026-04-01")
    assert len(rows) == 1 and rows[0]["net_sales"] == "-200.0000"
    assert rows[0]["purchase_count"] == 0 and rows[0]["last_purchase_date"] is None
    assert rows[0]["days_since_purchase"] is None and not rows[0]["inactive"]
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["net_sales"] == "-200.0000"


def test_unknown_stock_loss_period_is_explicitly_unavailable():
    stock, _ = stock_for(document())
    values = VALUES | {"date_from": "2026-05-01", "date_to": "2026-05-31"}
    rows, evidence = expenses(financial(), [], [], values, "INR", view="writeoffs", stock=stock)
    assert rows == []
    assert any("unavailable" in note.lower() for note in evidence["analytics"]["notices"])


def test_reduction_search_matches_diagnostic_labels_without_changing_posted_profit():
    sale = document()
    sale["components"] = [{"purpose": "DISCOUNT", "amount": "-100"}]
    rows, evidence = expenses(
        financial(),
        [],
        [],
        VALUES | {"search": "discount"},
        "INR",
        view="reductions",
        sales_documents=[sale],
    )
    assert len(rows) == 1 and rows[0]["amount"] == "100.0000"
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["net_profit"] == "700.0000"


def test_opening_adjustments_reconcile_cash_balances_without_inflating_receipts():
    data = inputs()
    data["periods"]["CURRENT"]["lines"].append(
        {
            "account_id": "cash",
            "posting_date": "2026-04-20",
            "side": "DEBIT",
            "base_amount": "75",
            "opening_effect": True,
        }
    )
    _, evidence = cash(data, VALUES, stock_index([]), "INR")
    amounts = evidence["analytics"]["amounts"]["CURRENT"]["INR"]
    assert amounts["cash_adjustments"] == "75.0000" and amounts["cash_receipts"] == "500.0000"
    assert Decimal(amounts["opening_cash"]) + Decimal(amounts["cash_receipts"]) - Decimal(
        amounts["cash_payments"]
    ) + Decimal(amounts["cash_adjustments"]) == Decimal(amounts["closing_cash"])


def test_profit_search_matches_unmapped_display_labels_without_inventing_cost():
    sale = document()
    sale["supplies"][0]["supply_kind"] = "ACCOUNT"
    rows, _ = profit(
        financial(),
        [],
        [sale],
        VALUES | {"search": "Unmapped account"},
        stock_index([]),
        "INR",
        view="products",
    )
    assert len(rows) == 1 and rows[0]["cost"] is None
    assert rows[0]["label"] == "Unmapped account lines"


def test_expense_group_search_uses_group_label_and_retains_all_group_accounts():
    statements = financial()
    for row in statements:
        if row["row_kind"] == "EXPENSE":
            row.update(group_id="expenses", group_name="Business expenses")
    rows, evidence = expenses(
        statements,
        [],
        [],
        VALUES | {"search": "Business expenses"},
        "INR",
        view="groups",
    )
    assert len(rows) == 1 and rows[0]["amount"] == "500.0000"
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["net_profit"] == "700.0000"


def test_foreign_stock_snapshot_does_not_claim_base_currency_value_even_if_empty():
    stock, _ = stock_for(document())
    stock["coverage"]["currency"] = "USD"
    stock["positions"] = {}
    _, evidence = cash(inputs(), VALUES, stock, "INR")
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["stock_tied_up"] is None


def test_owned_stock_value_and_slow_stock_use_complete_dated_positions():
    stock, _ = stock_for(document())
    rows, evidence = cash(inputs(), VALUES | {"slow_stock_days": 20}, stock, "INR", view="stock")
    amounts = evidence["analytics"]["amounts"]["CURRENT"]["INR"]
    assert len(rows) == 3  # 60 and 10 owned pieces, 2 kg; third-party 5 pieces excluded.
    assert amounts["stock_tied_up"] == "720.0000" and amounts["slow_stock"] == "720.0000"
    assert all(row["stock_status"] == "SLOW_MOVING" for row in rows)


def test_recent_company_item_demand_keeps_all_its_positions_out_of_slow_stock():
    stock, _ = stock_for(document())
    for movement in stock["movements"]:
        if movement["action"] == "SALE":
            movement["effective_date"] = "2026-04-25"
    rows, evidence = cash(inputs(), VALUES | {"slow_stock_days": 20}, stock, "INR", view="stock")
    amounts = evidence["analytics"]["amounts"]["CURRENT"]["INR"]
    assert amounts["stock_tied_up"] == "720.0000" and amounts["slow_stock"] == "20.0000"
    assert sum(row["stock_status"] == "RECENT_OR_MOVING" for row in rows) == 2


@pytest.mark.parametrize("missing", ["origins", "history"])
def test_unknown_stock_age_retains_known_value_without_claiming_slow_stock(missing):
    stock, _ = stock_for(document())
    if missing == "origins":
        stock["coverage"]["origins_complete"] = False
    days = 20 if missing == "origins" else 90
    rows, evidence = cash(inputs(), VALUES | {"slow_stock_days": days}, stock, "INR", view="stock")
    amounts = evidence["analytics"]["amounts"]["CURRENT"]["INR"]
    assert amounts["stock_tied_up"] == "720.0000" and amounts["slow_stock"] is None
    assert all(row["stock_status"] == "AGE_UNAVAILABLE" for row in rows)


def test_cash_comparison_retains_separate_balances_and_exact_changes():
    data = inputs()
    data["periods"]["COMPARATIVE"] = {"lines": [], "movements": [], "bills": []}
    values = VALUES | {"comparative_from": "2026-03-01", "comparative_to": "2026-03-31"}
    rows, evidence = cash(data, values, stock_index([]), "INR")
    current = [row for row in rows if row["period"] == "CURRENT"]
    assert all(row["comparison_amount"] == "0.0000" for row in current)
    assert sum(Decimal(row["change_amount"]) for row in current) == Decimal("1500")
    assert evidence["analytics"]["amounts"]["COMPARATIVE"]["INR"]["closing_cash"] == "0.0000"
