"""Full-result metrics are independent of paging and do not mix physical grains."""

from inventory_fixture import inventory_records

from reports.domain.reporting.inventory import calculate


def test_warehouse_totals_keep_units_and_ownership_separate():
    from inventory_fixture import inventory_records

    records, _ = inventory_records()
    rows, evidence = calculate("LOCATION_STOCK", records, {"as_of": "2026-04-30"})
    metrics = evidence["inventory_metrics"]
    assert metrics["location_count"] == 1
    assert metrics["owned_value"] == "720.0000"
    assert {r["unit"] for r in metrics["quantities"]} == {"PCS", "KG"}
    assert len(metrics["quantities"]) == 3
    assert len(rows) == metrics["row_count"]


def test_valuation_totals_exclude_gl_and_cost_detail_rows():
    from inventory_fixture import inventory_records

    records, _ = inventory_records()
    rows, evidence = calculate("STOCK_VALUATION", records, {"as_of": "2026-04-30"})
    metrics = evidence["inventory_metrics"]
    assert metrics["owned_value"] == "720.0000"
    assert metrics["balance_count"] == 3
    assert len(rows) > metrics["balance_count"]


def test_batch_totals_exclude_history_and_keep_lot_scope():
    from inventory_fixture import inventory_records

    from reports.domain.reporting.drilldowns import parameters_for

    records, ids = inventory_records()
    rows, evidence = calculate(
        "BATCH_SUMMARY", records, {"as_of": "2026-04-30", "include_history": True}
    )
    metrics = evidence["inventory_metrics"]
    assert metrics["batch_count"] == 2
    assert metrics["balance_count"] == 3
    from decimal import Decimal

    assert sum(Decimal(row["quantity"]) for row in metrics["quantities"]) == Decimal("75")
    row = next(row for row in rows if row.get("lot_id"))
    result = parameters_for(
        "stock_item_entries", {"as_of": "2026-04-30"}, row, coverage="2026-04-01"
    )
    assert result["lot_id"] == row["lot_id"]


def test_expiry_metrics_count_exception_positions_only():
    from inventory_fixture import inventory_records

    records, _ = inventory_records()
    rows, evidence = calculate(
        "STOCK_EXPIRY", records, {"as_of": "2026-04-30", "days_ahead": 90, "include_expired": True}
    )
    metrics = evidence["inventory_metrics"]
    assert metrics["expired_count"] == 1
    assert metrics["near_expiry_count"] == 2
    assert metrics["unknown_expiry_count"] == 0
    assert metrics["owned_value"] == "700.0000"


def test_reorder_eligible_basis_remains_explicit_without_reservations():
    records, _ = inventory_records()
    next(r["payload"] for r in records if r["payload"]["kind"] == "COVERAGE")[
        "reservations_complete"
    ] = False
    rows, evidence = calculate(
        "STOCK_REORDER",
        records,
        {
            "as_of": "2026-04-30",
            "quantity_basis": "ELIGIBLE",
            "only_shortages": False,
            "include_orders": False,
        },
    )
    assert rows and all(row["quantity_basis"] == "ELIGIBLE" for row in rows)
    assert all(row["available"] is None for row in rows)
    assert evidence["inventory_metrics"]["row_count"] == len(rows)


def test_reorder_respects_native_warehouse_band_multiple_and_maximum():
    import uuid

    records, ids = inventory_records()
    item = next(
        r["payload"]
        for r in records
        if r["payload"].get("item_id") == ids["item"] and r["payload"]["kind"] == "ITEM"
    )
    item["replenishment"] = [
        {
            "policy_id": str(uuid.uuid4()),
            "location_id": ids["location"],
            "reorder_level": "80",
            "target_level": "100",
            "minimum_order": "10",
            "maximum_order": "30",
            "order_multiple": "10",
        }
    ]
    rows, evidence = calculate(
        "STOCK_REORDER",
        records,
        {
            "as_of": "2026-04-30",
            "quantity_basis": "AVAILABLE",
            "only_shortages": True,
            "include_orders": False,
            "item_id": ids["item"],
            "location_id": ids["location"],
        },
    )
    assert len(rows) == 1
    assert rows[0]["projected_available"] == "55.0000"
    assert rows[0]["suggested_quantity"] == "30.0000"
    assert rows[0]["shortfall_after_order"] == "15.0000"
    assert evidence["inventory_metrics"]["limited_count"] == 1


def test_ageing_metrics_separate_unknown_age_without_adding_cohort_balances_twice():
    records, _ = inventory_records()
    next(row["payload"] for row in records if row["payload"]["kind"] == "POSITION")["origins"][
        0
    ].update(receipt_date=None, provenance="UNKNOWN")
    rows, evidence = calculate(
        "STOCK_AGEING",
        records,
        {"as_of": "2026-04-30", "age_basis": "RECEIPT", "buckets": [30, 60, 90, 180]},
    )
    metrics = evidence["inventory_metrics"]
    assert metrics["unknown_count"] == 1
    assert metrics["cohort_count"] == 4
    assert metrics["age_buckets"]


def test_movement_totals_and_drill_retain_the_requested_period():
    from reports.domain.reporting.drilldowns import parameters_for

    records, _ = inventory_records()
    parameters = {
        "as_of": "2026-04-30",
        "date_from": "2026-04-05",
        "nonmoving_days": 90,
        "only_nonmoving": False,
    }
    rows, evidence = calculate("STOCK_MOVEMENT", records, parameters)
    metrics = evidence["inventory_metrics"]
    own = next(
        row for row in metrics["quantities"] if row["unit"] == "PCS" and row["owner"] == "OWN"
    )
    assert own["opening"] == "110.0000" and own["outward"] == "40.0000"
    child = parameters_for("stock_item_entries", parameters, rows[0], "2026-04-01")
    assert child["date_from"] == "2026-04-05"


def test_group_totals_do_not_add_overlapping_ancestor_rows():
    records, _ = inventory_records()
    rows, evidence = calculate("STOCK_GROUP_SUMMARY", records, {"as_of": "2026-04-30"})
    assert len(rows) > len(evidence["inventory_metrics"]["quantities"])
    assert evidence["inventory_metrics"]["owned_value"] == "720.0000"
    assert evidence["inventory_metrics"]["item_count"] == 2


def test_item_ledger_metrics_reconcile_positions_without_adding_running_balances():
    records, ids = inventory_records()
    _, evidence = calculate(
        "ITEM_LEDGER",
        records,
        {"as_of": "2026-04-30", "date_from": "2026-04-05", "item_id": ids["item"]},
    )
    metrics = evidence["inventory_metrics"]
    assert metrics["code"] == "ITEM_LEDGER"
    assert metrics["item_count"] == 1 and metrics["entry_count"] == 1
    assert metrics["owned_value"] == "700.0000"
    own = next(row for row in metrics["quantities"] if row["owner"] == "OWN")
    assert {key: own[key] for key in ("opening", "inward", "outward", "quantity")} == {
        "opening": "110.0000",
        "inward": "0.0000",
        "outward": "40.0000",
        "quantity": "70.0000",
    }


def test_item_ledger_metrics_keep_unknown_values_unavailable():
    records, ids = inventory_records()
    records[0]["payload"]["valuation_complete"] = False
    _, evidence = calculate(
        "ITEM_LEDGER",
        records,
        {"as_of": "2026-04-30", "date_from": "2026-04-05", "item_id": ids["item"]},
    )
    assert evidence["inventory_metrics"]["owned_value"] is None
