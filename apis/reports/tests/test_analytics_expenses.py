from analytics_fixture import VALUES, document, stock_for
from test_analytics_profit import financial

from reports.domain.analytics_expenses import calculate


def test_expenses_reconcile_and_purchase_spending_is_not_added_to_pnl():
    purchase = document("10000") | {"invoice_kind": "PURCHASE"}
    rows, evidence = calculate(financial(), [], [purchase], VALUES, "INR", view="suppliers")
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["total_expenses"] == "500.0000"
    assert rows[0]["amount"] == "10000.0000"
    assert rows[0]["invoice_count"] == 1


def test_increases_require_materiality_and_explicit_comparison():
    values = VALUES | {
        "comparative_from": "2026-03-01",
        "comparative_to": "2026-03-31",
        "material_amount": "50",
        "increase_percent": 25,
    }
    current, prior = financial(), financial("COMPARATIVE")
    prior[2]["amount"] = "40"
    rows, _ = calculate(current + prior, [], [], values, "INR", view="exceptions")
    assert len(rows) == 1 and rows[0]["account_id"] == "rent"
    assert rows[0]["exception"] == "MATERIAL_INCREASE"
    assert rows[0]["change_amount"] == "60.0000"
    assert calculate(current, [], [], VALUES, "INR", view="exceptions")[0] == []


def test_new_spending_and_groups_do_not_double_count_parent_rollups():
    current = financial()
    for row in current:
        if row["row_kind"] == "EXPENSE":
            row.update(group_id="costs", group_name="Costs")
    rows, _ = calculate(current, [], [], VALUES, "INR", view="groups")
    assert len(rows) == 1 and rows[0]["amount"] == "500.0000"
    values = VALUES | {
        "comparative_from": "2026-03-01",
        "comparative_to": "2026-03-31",
        "material_amount": "50",
    }
    rows, _ = calculate(current, [], [], values, "INR", view="exceptions")
    assert all(row["exception"] == "NEW_OR_RESUMED_SPENDING" for row in rows)


def test_purchase_returns_reduce_commercial_spending_once_and_currencies_stay_separate():
    bought = document("1000") | {"invoice_kind": "PURCHASE"}
    returned = document("200") | {"invoice_kind": "DEBIT_NOTE", "party_id": bought["party_id"]}
    dollars = document("30", currency="USD") | {"invoice_kind": "PURCHASE"}
    rows, _ = calculate(
        financial(), [], [bought, returned, dollars], VALUES, "INR", view="suppliers"
    )
    assert next(row["amount"] for row in rows if row["currency"] == "INR") == "800.0000"
    assert next(row["amount"] for row in rows if row["currency"] == "USD") == "30.0000"


def test_reductions_and_stock_losses_are_diagnostics_without_reducing_profit_again():
    sale = document("1000")
    sale["components"] = [{"purpose": "DISCOUNT", "amount": "-100"}]
    rows, evidence = calculate(
        financial(), [], [], VALUES, "INR", view="reductions", sales_documents=[sale]
    )
    assert next(row["amount"] for row in rows if row["metric"] == "discounts") == "100.0000"
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["net_profit"] == "700.0000"
    stock, _ = stock_for(sale)
    movement = next(item for item in stock["movements"] if item["action"] == "SALE")
    stock["movements"].append(
        movement | {"action": "DISPOSAL", "quantity_delta": "-2", "value_delta": "-20"}
    )
    rows, _ = calculate(financial(), [], [], VALUES, "INR", view="writeoffs", stock=stock)
    assert rows[0]["amount"] == "20.0000"
