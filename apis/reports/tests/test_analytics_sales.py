import pytest
from analytics_fixture import VALUES, document, stock_for
from billing_platform.errors import ConflictError

from reports.domain.analytics_common import stock_index
from reports.domain.analytics_sales import calculate
from reports.schemas.analytics import AnalyticsParameters


def test_sales_count_invoices_once_exclude_returns_once_and_separate_currencies():
    sale = document("1000")
    sale["components"] = [
        {"purpose": "DISCOUNT", "amount": "-100"},
        {"purpose": "FREIGHT", "amount": "25"},
    ]
    returned = document("200", kind="CREDIT_NOTE", party=sale["party_id"])
    other = document("50", currency="USD", party=sale["party_id"])
    rows, evidence = calculate([sale, returned, other], VALUES, stock_index([]))
    amounts = evidence["analytics"]["amounts"]["CURRENT"]
    assert amounts["INR"]["net_sales"] == "800.0000"
    assert amounts["INR"]["discounts"] == "100.0000"
    assert amounts["INR"]["invoice_count"] == 1
    assert amounts["INR"]["average_invoice"] == "1000.0000"
    assert amounts["USD"]["net_sales"] == "50.0000"
    assert len(rows) == 2


def test_native_signed_discount_is_displayed_as_a_positive_reduction():
    sale = document()
    sale["components"] = [{"purpose": "DISCOUNT", "amount": "-100"}]
    _, evidence = calculate([sale], VALUES, stock_index([]))
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["discounts"] == "100.0000"


def test_product_joins_common_line_and_retains_exact_actual_quantity():
    sale = document()
    stock, ids = stock_for(sale)
    rows, _ = calculate([sale], VALUES, stock, view="products")
    assert rows[0]["item_id"] == ids["item"]
    assert rows[0]["quantity"] == "40.0000"
    assert rows[0]["net_sales"] == "1000.0000"
    assert rows[0]["unit"] == "PCS"


def test_legacy_product_links_are_not_guessed_from_descriptions():
    sale = document()
    stock, _ = stock_for(sale)
    sale["supplies"][0].pop("item_line_key")
    rows, evidence = calculate([sale], VALUES, stock, view="products")
    assert rows[0]["item_id"] is None and rows[0]["quantity"] is None
    assert evidence["analytics"]["notices"][-1].startswith("Some goods lack verified")


def test_comparison_and_zero_denominator_are_explicit():
    sale = document()
    prior = document("500", day="2026-03-10", party=sale["party_id"])
    values = VALUES | {"comparative_from": "2026-03-01", "comparative_to": "2026-03-31"}
    rows, _ = calculate([sale, prior], values, stock_index([]))
    current = next(row for row in rows if row["period"] == "CURRENT")
    assert current["comparison_amount"] == "500.0000" and current["change_percent"] == "100.0000"
    rows, _ = calculate([sale], values, stock_index([]))
    assert rows[0]["comparison_amount"] == "0.0000" and rows[0]["change_percent"] is None


def test_unbalanced_supply_amount_is_rejected_before_product_projection():
    sale = document()
    sale["supplies"][0]["commercial"] = "999"
    with pytest.raises(ConflictError, match="commercial lines"):
        calculate([sale], VALUES, stock_index([]), view="products")


def test_search_and_empty_scope_do_not_create_fictional_sales():
    assert AnalyticsParameters.model_validate(VALUES).search == ""
    sale = document()
    rows, evidence = calculate([sale], VALUES | {"search": "Absent"}, stock_index([]))
    assert rows == [] and evidence["analytics"]["amounts"]["CURRENT"] == {}
    with pytest.raises(ValueError):
        AnalyticsParameters.model_validate(VALUES | {"search": "a"})
    with pytest.raises(ValueError):
        AnalyticsParameters.model_validate(VALUES | {"date_to": "2026-03-31"})
