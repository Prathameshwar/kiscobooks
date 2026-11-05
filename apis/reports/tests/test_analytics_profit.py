from analytics_fixture import VALUES, document, stock_for

from reports.domain.analytics_profit import calculate


def financial(period="CURRENT"):
    return [
        {
            "row_kind": "INCOME",
            "amount": "1200",
            "affects_gross_profit": True,
            "account_name": "Sales",
            "account_id": "sales",
            "currency": "INR",
            "period": period,
        },
        {
            "row_kind": "EXPENSE",
            "amount": "400",
            "affects_gross_profit": True,
            "account_name": "Cost",
            "account_id": "cost",
            "currency": "INR",
            "period": period,
        },
        {
            "row_kind": "EXPENSE",
            "amount": "100",
            "affects_gross_profit": False,
            "account_name": "Rent",
            "account_id": "rent",
            "currency": "INR",
            "period": period,
        },
        *(
            {"row_kind": key, "amount": value, "period": period}
            for key, value in (
                ("TOTAL_INCOME", "1200"),
                ("TOTAL_EXPENSE", "500"),
                ("GROSS_PROFIT", "800"),
                ("NET_PROFIT", "700"),
            )
        ),
    ]


def test_company_profit_and_cost_breakdown_reconcile_to_existing_pnl_totals():
    sale = document()
    stock, _ = stock_for(sale)
    rows, evidence = calculate(financial(), [], [sale], VALUES, stock, "INR")
    totals = evidence["analytics"]["amounts"]["CURRENT"]["INR"]
    assert totals["gross_profit"] == "800.0000"
    assert totals["operating_expenses"] == "100.0000"
    assert totals["net_profit"] == "700.0000"
    assert next(row["amount"] for row in rows if row["metric"] == "net_profit") == "700.0000"


def test_item_margin_uses_the_actual_sale_cost_instead_of_latest_purchase_price():
    sale = document()
    stock, _ = stock_for(sale)
    rows, _ = calculate(financial(), [], [sale], VALUES, stock, "INR", view="products")
    assert rows[0]["cost"] == "400.0000"
    assert rows[0]["gross_profit"] == "600.0000"
    assert rows[0]["margin_percent"] == "60.0000"


def test_missing_cost_or_mismatched_currency_never_becomes_zero_cost_profit():
    sale = document(currency="USD")
    stock, _ = stock_for(sale)
    rows, _ = calculate(financial(), [], [sale], VALUES, stock, "INR", view="products")
    assert rows[0]["cost"] is None and rows[0]["margin_percent"] is None


def test_margin_recomputes_from_combined_operands():
    first = document("1000")
    stock, _ = stock_for(first)
    second = document("2000")
    second["voucher_id"] = first["voucher_id"]
    second["supplies"][0]["item_line_key"] = first["supplies"][0]["item_line_key"]
    # Different invoices cannot validly own the same voucher/stock line. Exercise
    # aggregation with an independent duplicate-shaped native cost movement.
    movement = next(row for row in stock["movements"] if row["action"] == "SALE")
    second["voucher_id"] = "01990000-0000-7000-8000-000000000099"
    stock["movements"].append(
        movement | {"voucher_id": second["voucher_id"], "value_delta": "-1000"}
    )
    rows, _ = calculate(financial(), [], [first, second], VALUES, stock, "INR", view="products")
    assert rows[0]["net_sales"] == "3000.0000" and rows[0]["cost"] == "1400.0000"
    assert rows[0]["margin_percent"] == "53.3333"
