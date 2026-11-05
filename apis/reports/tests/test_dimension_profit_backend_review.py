"""Backend review regressions for retained scope, precision and export context."""

from decimal import localcontext

import pytest
from analytics_fixture import VALUES, document, stock_for
from billing_platform.display import DisplayConfiguration
from test_presentation_rendering import FIXTURE

from reports.domain.analytics_dimension_profit import calculate
from reports.domain.reporting.drilldowns import parameters_for
from reports.rendering.analytics import metadata


def test_invoice_profit_drilldown_does_not_expand_to_the_buyers_other_invoices():
    sale = document()
    stock, _ = stock_for(sale)
    rows, _ = calculate("BUYER_PROFIT", [sale], VALUES, stock, view="invoices")
    selected = parameters_for("analytics_sales", VALUES, rows[0], VALUES["date_from"])
    assert selected["invoice_id"] == sale["invoice_id"]


def test_reference_filtered_buyer_drilldown_preserves_the_selected_invoice():
    first = document()
    second = document(party=first["party_id"])
    first["bill_reference"], second["bill_reference"] = "SALE-A", "SALE-B"
    stock, _ = stock_for(first)
    values = VALUES | {"search": "SALE-A"}
    rows, _ = calculate("BUYER_PROFIT", [first, second], values, stock)
    selected = parameters_for("analytics_sales", values, rows[0], VALUES["date_from"])
    assert selected["invoice_id"] == first["invoice_id"]


def test_multi_invoice_search_does_not_offer_a_broader_buyer_drilldown():
    first = document()
    second = document(party=first["party_id"])
    first["bill_reference"], second["bill_reference"] = "MATCH-A", "MATCH-B"
    stock, _ = stock_for(first)
    values = VALUES | {"search": "MATCH"}
    rows, _ = calculate("BUYER_PROFIT", [first, second], values, stock)
    assert parameters_for("analytics_sales", values, rows[0], VALUES["date_from"]) is None
    # Searching the buyer name covers the complete buyer and can safely drill.
    values = VALUES | {"search": "Buyer"}
    rows, _ = calculate("BUYER_PROFIT", [first, second], values, stock)
    assert (
        parameters_for("analytics_sales", values, rows[0], VALUES["date_from"])["party_id"]
        == first["party_id"]
    )


def test_dimension_profit_owns_precision_for_commercial_and_stock_arithmetic():
    sale = document("123456789.1234")
    stock, _ = stock_for(sale)
    with localcontext() as caller:
        caller.prec = 6
        rows, evidence = calculate("BUYER_PROFIT", [sale], VALUES, stock)
        assert caller.prec == 6
    assert rows[0]["gross_profit"] == "123456389.1234"
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["net_sales"] == "123456789.1234"


def test_exports_retain_buyer_product_group_and_currency_selection():
    evidence = {
        "analytics": {
            "calculation_version": 3,
            "amounts": {},
            "notices": [],
            "selected_filters": {
                "party_id": "Buyer A",
                "item_id": "ITEM / Widget",
                "group_id": "All / Child",
                "currency": "INR",
            },
        }
    }
    retained = dict(metadata(evidence, {}, DisplayConfiguration(**FIXTURE["config"])))
    assert retained["Buyer"] == "Buyer A"
    assert retained["Product"] == "ITEM / Widget"
    assert retained["Product group"] == "All / Child"
    assert retained["Document currency"] == "INR"


def test_anonymous_invoice_drilldown_and_comparative_dates_stay_exact():
    sale = document(day="2026-03-10")
    sale["party_id"] = None
    stock, _ = stock_for(sale)
    values = VALUES | {"comparative_from": "2026-03-01", "comparative_to": "2026-03-31"}
    rows, _ = calculate("BUYER_PROFIT", [sale], values, stock, view="invoices")
    result = parameters_for("analytics_sales", values, rows[0], "2026-01-01")
    assert result == {
        "date_from": "2026-03-01",
        "date_to": "2026-03-31",
        "currency": "INR",
        "invoice_id": sale["invoice_id"],
    }


def test_legacy_filtered_buyer_row_without_subset_proof_does_not_expand():
    sale = document()
    row = {
        "row_kind": "BUYER_PROFIT",
        "party_id": sale["party_id"],
        "currency": "INR",
        "period": "CURRENT",
    }
    assert (
        parameters_for("analytics_sales", VALUES | {"search": "INV"}, row, VALUES["date_from"])
        is None
    )
    assert (
        parameters_for("analytics_sales", VALUES, row, VALUES["date_from"])["party_id"]
        == sale["party_id"]
    )


@pytest.mark.parametrize("view", ["default", "groups"])
def test_unmapped_prior_sales_do_not_become_zero_product_comparison_profit(view):
    current = document()
    prior = document("300", day="2026-03-10", party=current["party_id"])
    stock, ids = stock_for(current)
    values = VALUES | {
        "comparative_from": "2026-03-01",
        "comparative_to": "2026-03-31",
        "item_id": ids["item"],
    }
    rows, _ = calculate("PRODUCT_PROFIT", [current, prior], values, stock, view=view)
    assert rows and all(row["period"] == "CURRENT" for row in rows)
    assert all(row["comparison_amount"] is None and row["change_amount"] is None for row in rows)
