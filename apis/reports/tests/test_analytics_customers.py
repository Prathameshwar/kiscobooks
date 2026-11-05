import uuid

from analytics_fixture import VALUES, document

from reports.domain.analytics_customers import calculate


def test_repeat_customers_use_complete_recorded_history_not_only_period_purchases():
    party = str(uuid.uuid4())
    previous = document("500", day="2026-03-10", party=party)
    current = document("1000", party=party)
    rows, evidence = calculate([previous, current], VALUES, "2026-01-01")
    assert rows[0]["segment"] == "REPEAT"
    assert rows[0]["purchase_count"] == 1
    assert rows[0]["recorded_purchase_count"] == 2
    assert rows[0]["recorded_sales"] == "1500.0000"
    assert evidence["analytics"]["amounts"]["CURRENT"]["INR"]["repeat_rate"] == "100.0000"


def test_inactivity_and_first_observed_have_explicit_asof_and_history_windows():
    older = document(day="2026-01-01")
    first = document()
    rows, evidence = calculate([older, first], VALUES | {"inactive_days": 90}, "2026-01-01")
    assert (
        next(row for row in rows if row["party_id"] == older["party_id"])["segment"] == "INACTIVE"
    )
    assert (
        next(row for row in rows if row["party_id"] == first["party_id"])["segment"]
        == "FIRST_OBSERVED"
    )
    assert "First observed does not mean first ever" in evidence["analytics"]["notices"][0]


def test_customer_reference_search_does_not_remove_other_purchase_history():
    current = document()
    previous = document("500", day="2026-03-10", party=current["party_id"])
    rows, _ = calculate(
        [current, previous], VALUES | {"search": current["bill_reference"]}, "2026-01-01"
    )
    assert rows[0]["recorded_purchase_count"] == 2 and rows[0]["repeat"]


def test_unidentified_sales_are_separate_from_customer_segments():
    unidentified = document()
    unidentified["party_id"] = None
    rows, evidence = calculate([unidentified], VALUES, "2026-01-01")
    assert rows == []
    assert evidence["analytics"]["unidentified_invoices"]["CURRENT"] == 1


def test_declining_customer_filter_keeps_comparison_and_purchase_drilldown_scope():
    current = document("100")
    prior = document("500", day="2026-03-10", party=current["party_id"])
    values = VALUES | {
        "comparative_from": "2026-03-01",
        "comparative_to": "2026-03-31",
        "segment": "DECLINING",
    }
    rows, _ = calculate([current, prior], values, "2026-01-01")
    assert rows[0]["segment"] == "DECLINING"
    assert rows[0]["change_amount"] == "-400.0000"
    purchases, _ = calculate([current, prior], values, "2026-01-01", view="purchases")
    assert {row["invoice_id"] for row in purchases} == {current["invoice_id"], prior["invoice_id"]}
