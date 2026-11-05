"""Independent commercial gross-profit examples for buyer and product reports."""

from copy import deepcopy

import pytest
from analytics_fixture import VALUES, document, stock_for

from reports.domain.analytics_dimension_profit import calculate
from reports.domain.reporting.drilldowns import parameters_for
from reports.schemas.analytics import BuyerProfitParameters, ProductProfitParameters


def test_buyer_profit_and_invoice_view_use_actual_cost_and_returns():
    sale = document()
    stock, _ = stock_for(sale)
    credit = document("200", kind="CREDIT_NOTE", party=sale["party_id"])
    movement = next(row for row in stock["movements"] if row["action"] == "SALE")
    stock["movements"].append(
        movement
        | {
            "voucher_id": credit["voucher_id"],
            "line_id": credit["supplies"][0]["item_line_key"],
            "action": "CUSTOMER_RETURN",
            "value_delta": "80",
            "quantity_delta": "1",
        }
    )
    rows, evidence = calculate("BUYER_PROFIT", [sale, credit], VALUES, stock)
    assert len(rows) == 1
    assert rows[0]["net_sales"] == "800.0000"
    assert rows[0]["cost"] == "320.0000"
    assert rows[0]["gross_profit"] == "480.0000"
    assert rows[0]["margin_percent"] == "60.0000"
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["gross_profit"] == "480.0000"
    invoices, _ = calculate("BUYER_PROFIT", [sale, credit], VALUES, stock, view="invoices")
    assert len(invoices) == 2
    assert {row["gross_profit"] for row in invoices} == {"600.0000", "-120.0000"}


def test_partial_costs_hide_aggregate_profit_and_preserve_currency_groups():
    sale = document()
    stock, _ = stock_for(sale)
    unknown = document("300", party=sale["party_id"])
    foreign = document("20", currency="USD", party=sale["party_id"])
    rows, evidence = calculate("BUYER_PROFIT", [sale, unknown, foreign], VALUES, stock)
    local = next(row for row in rows if row["currency"] == "INR")
    assert local["net_sales"] == "1300.0000"
    assert local["cost"] is local["gross_profit"] is local["margin_percent"] is None
    assert local["cost_status"] == "COST_UNAVAILABLE"
    amounts = evidence["analytics"]["amounts"]["CURRENT"]
    assert set(amounts) == {"INR", "USD"}
    assert amounts["INR"]["unavailable_line_count"] == 1
    assert amounts["USD"]["gross_profit"] is None


def test_filters_apply_to_buyer_totals_and_unknown_buyers_are_explicit():
    first = document()
    stock, _ = stock_for(first)
    second = document("100")
    second["customer_name"] = second["account_name"] = "Another buyer"
    rows, evidence = calculate(
        "BUYER_PROFIT", [first, second], VALUES | {"party_id": first["party_id"]}, stock
    )
    assert (
        len(rows) == 1
        and evidence["analytics"]["amounts"]["CURRENT"]["INR"]["net_sales"] == "1000.0000"
    )
    second["party_id"] = None
    rows, _ = calculate("BUYER_PROFIT", [second], VALUES, stock)
    assert rows[0]["label"] == "Unidentified buyer"
    rows, _ = calculate("BUYER_PROFIT", [second], VALUES | {"search": "Unidentified"}, stock)
    assert len(rows) == 1


def test_unknown_comparison_cost_is_not_treated_as_zero_profit():
    current = document()
    stock, _ = stock_for(current)
    prior = document("300", day="2026-03-10", party=current["party_id"])
    rows, _ = calculate(
        "BUYER_PROFIT",
        [current, prior],
        VALUES
        | {
            "comparative_from": "2026-03-01",
            "comparative_to": "2026-03-31",
        },
        stock,
    )
    row = next(row for row in rows if row["period"] == "CURRENT")
    assert row["gross_profit"] == "600.0000"
    assert row["comparison_amount"] is row["change_amount"] is row["change_percent"] is None


def test_empty_and_zero_sales_do_not_invent_margins_or_mutate_input():
    sale = document("0")
    stock, _ = stock_for(sale)
    before = deepcopy((sale, stock))
    rows, _ = calculate("BUYER_PROFIT", [sale], VALUES, stock)
    assert rows[0]["gross_profit"] == "-400.0000" and rows[0]["margin_percent"] is None
    assert (sale, stock) == before
    rows, evidence = calculate("BUYER_PROFIT", [], VALUES, stock)
    assert rows == [] and evidence["analytics"]["amounts"]["CURRENT"] == {}


def test_product_groups_include_ancestors_without_duplicate_lines_or_kpis():
    sale = document()
    stock, ids = stock_for(sale)
    rows, evidence = calculate("PRODUCT_PROFIT", [sale], VALUES, stock, view="groups")
    assert len(rows) == 2  # The product is assigned to both its parent and child.
    assert {row["group_id"] for row in rows} == {ids["group"], ids["child"]}
    assert all(row["gross_profit"] == "600.0000" for row in rows)
    assert {row["label"] for row in rows} == {"All", "All / Child"}
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["net_sales"] == "1000.0000"
    assert any("not additive" in note for note in evidence["analytics"]["notices"])
    products, _ = calculate("PRODUCT_PROFIT", [sale], VALUES | {"group_id": ids["child"]}, stock)
    assert len(products) == 1 and products[0]["item_id"] == ids["item"]


def test_product_group_search_and_product_filters_have_consistent_totals():
    sale = document()
    stock, ids = stock_for(sale)
    rows, evidence = calculate(
        "PRODUCT_PROFIT", [sale], VALUES | {"search": "child"}, stock, view="groups"
    )
    assert len(rows) == 1 and rows[0]["group_id"] == ids["child"]
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["gross_profit"] == "600.0000"
    rows, evidence = calculate("PRODUCT_PROFIT", [sale], VALUES | {"item_id": ids["kg"]}, stock)
    assert rows == [] and evidence["analytics"]["amounts"]["CURRENT"] == {}


def test_unmapped_lines_are_separate_from_verified_ungrouped_products():
    sale = document()
    stock, ids = stock_for(sale)
    stock["items"][ids["item"]]["group_ids"] = []
    service = document("200")
    service["supplies"][0]["supply_kind"] = "SERVICE"
    rows, evidence = calculate("PRODUCT_PROFIT", [sale, service], VALUES, stock, view="groups")
    assert {row["label"] for row in rows} == {"Ungrouped products", "Unmapped service lines"}
    assert (
        next(row for row in rows if row["label"] == "Ungrouped products")["gross_profit"]
        == "600.0000"
    )
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["gross_profit"] is None


def test_product_margin_recomputes_ratio_and_never_combines_product_quantities():
    first = document("1000")
    stock, ids = stock_for(first)
    second = document("2000")
    movement = next(row for row in stock["movements"] if row["action"] == "SALE")
    stock["movements"].append(
        movement
        | {
            "voucher_id": second["voucher_id"],
            "line_id": second["supplies"][0]["item_line_key"],
            "item_id": ids["kg"],
            "position_id": ids["bulk"],
            "value_delta": "-1000",
        }
    )
    rows, evidence = calculate("PRODUCT_PROFIT", [first, second], VALUES, stock, view="groups")
    assert all(row["margin_percent"] == "53.3333" for row in rows)
    assert all("quantity" not in row for row in rows)
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["gross_profit"] == "1600.0000"


def test_group_drilldown_preserves_currency_period_and_selection_without_expanding_scope():
    group = "01990000-0000-7000-8000-000000000001"
    item = "01990000-0000-7000-8000-000000000002"
    values = VALUES | {
        "search": "Child",
        "item_id": item,
        "comparative_from": "2026-03-01",
        "comparative_to": "2026-03-31",
    }
    row = {"group_id": group, "currency": "USD", "period": "COMPARATIVE"}
    result = parameters_for("profit_group_products", values, row, "2026-01-01")
    assert result == {
        "group_id": group,
        "item_id": item,
        "currency": "USD",
        "date_from": "2026-03-01",
        "date_to": "2026-03-31",
    }
    assert (
        parameters_for("profit_group_products", values | {"group_id": item}, row, "2026-01-01")
        is None
    )
    assert (
        parameters_for("profit_group_products", values, row | {"group_id": None}, "2026-01-01")
        is None
    )


@pytest.mark.parametrize("model", [BuyerProfitParameters, ProductProfitParameters])
def test_profit_filters_validate_identity_search_currency_period_and_no_unused_grain(model):
    valid = {"date_from": "2026-04-01", "date_to": "2026-04-30", "search": "  Buyer   One "}
    assert model.model_validate(valid).search == "Buyer One"
    for update in (
        {"party_id": "bad"},
        {"currency": "usd"},
        {"search": "x"},
        {"grain": "MONTH"},
        {"date_from": "2000-01-01"},
    ):
        with pytest.raises(ValueError):
            model.model_validate(valid | update)


def test_missing_and_complete_prior_costs_compare_by_identity_not_display_name():
    current = document()
    prior = document("500", day="2026-03-10", party=current["party_id"])
    prior["customer_name"] = "Former buyer name"
    stock, _ = stock_for(current)
    stock["coverage"]["history_start"] = "2026-03-01"
    movement = next(row for row in stock["movements"] if row["action"] == "SALE")
    stock["movements"].append(
        movement
        | {
            "voucher_id": prior["voucher_id"],
            "line_id": prior["supplies"][0]["item_line_key"],
            "effective_date": "2026-03-10",
            "value_delta": "-300",
        }
    )
    values = VALUES | {"comparative_from": "2026-03-01", "comparative_to": "2026-03-31"}
    rows, _ = calculate("BUYER_PROFIT", [current, prior], values, stock)
    row = next(row for row in rows if row["period"] == "CURRENT")
    assert (row["comparison_amount"], row["change_amount"], row["change_percent"]) == (
        "200.0000",
        "400.0000",
        "200.0000",
    )
    rows, _ = calculate("BUYER_PROFIT", [current], values, stock)
    assert rows[0]["comparison_amount"] == "0.0000" and rows[0]["change_percent"] is None
    unknown = document(party=current["party_id"])
    rows, _ = calculate("BUYER_PROFIT", [unknown, prior], values, stock)
    assert next(row for row in rows if row["period"] == "CURRENT")["change_amount"] is None


def test_product_search_currency_filter_and_invalid_hierarchy_fail_closed():
    sale = document()
    stock, ids = stock_for(sale)
    rows, _ = calculate(
        "PRODUCT_PROFIT", [sale], VALUES | {"search": "Item", "currency": "INR"}, stock
    )
    assert len(rows) == 1
    rows, _ = calculate("PRODUCT_PROFIT", [sale], VALUES | {"currency": "USD"}, stock)
    assert rows == []
    with pytest.raises(ValueError, match="unsupported"):
        calculate("PRODUCT_PROFIT", [sale], VALUES, stock, view="invoices")
    stock["groups"][ids["group"]]["parent_id"] = ids["child"]
    with pytest.raises(ValueError, match="cyclic"):
        calculate("PRODUCT_PROFIT", [sale], VALUES, stock)
