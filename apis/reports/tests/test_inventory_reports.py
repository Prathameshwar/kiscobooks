import datetime as dt
import uuid
from copy import deepcopy
from decimal import Decimal

import pytest
from inventory_fixture import inventory_records, parameters
from pydantic import ValidationError

from reports.domain.reporting.inventory import CODES, calculate
from reports.tasks.report_catalog import catalog


def run(code, records=None, **overrides):
    original, ids = inventory_records()
    entry = catalog().resolve(code)
    values = entry.handler.normalize(parameters(code, ids) | overrides)
    return calculate(code, records or original, values), ids


@pytest.mark.parametrize("code", CODES)
def test_ten_inventory_reports_are_typed_populated_and_deterministic(code):
    records, ids = inventory_records()
    entry = catalog().resolve(code)
    values = entry.handler.normalize(parameters(code, ids))
    first = calculate(code, records, values)
    assert first[0]
    assert first == calculate(code, list(reversed(records)), values)
    assert first[1]["inventory_coverage"]["as_of"] == "2026-04-30"
    with pytest.raises(ValidationError):
        entry.handler.normalize(values | {"unknown": "ignored?"})


def test_summary_does_not_double_subtract_held_expired_or_third_party_stock():
    (rows, _), ids = run("STOCK_SUMMARY")
    row = next(r for r in rows if r["item_id"] == ids["item"] and r["owner"] == "OWN")
    assert {
        key: row[key]
        for key in (
            "opening",
            "inward",
            "outward",
            "quantity",
            "eligible",
            "reserved",
            "available",
            "carrying_value",
        )
    } == {
        "opening": "110.0000",
        "inward": "0.0000",
        "outward": "40.0000",
        "quantity": "70.0000",
        "eligible": "60.0000",
        "reserved": "5.0000",
        "available": "55.0000",
        "carrying_value": "700.0000",
    }
    third = next(r for r in rows if r["owner"] == "THIRD_PARTY")
    assert third["quantity"] == "5.0000" and third["carrying_value"] is None
    assert third["available"] == "0.0000"


def test_ledger_opening_running_and_closing_reconcile_for_selected_period():
    (rows, _), ids = run("ITEM_LEDGER", date_from="2026-04-05")
    good = [r for r in rows if r["position_id"] == ids["good"]]
    assert [r["balance"] for r in good] == ["100.0000", "60.0000"]
    assert good[-1]["outward"] == "40.0000"
    assert good[-1]["voucher_number"] == "SALE-1"


@pytest.mark.parametrize(
    "start,opening,outward",
    [("2026-04-05", "110.0000", "40.0000"), ("2026-04-20", "70.0000", "0.0000")],
)
def test_final_review_movement_balances_use_requested_period(start, opening, outward):
    (rows, _), ids = run("STOCK_MOVEMENT", date_from=start)
    row = next(r for r in rows if r["item_id"] == ids["item"] and r["owner"] == "OWN")
    assert row["opening"] == opening
    assert row["inward"] == "0.0000"
    assert row["outward"] == outward
    assert Decimal(row["opening"]) + Decimal(row["inward"]) - Decimal(row["outward"]) == Decimal(
        row["quantity"]
    )


def test_final_review_minimum_life_requires_known_expiry():
    records, ids = inventory_records()
    good = next(
        r["payload"]
        for r in records
        if r["payload"]["kind"] == "POSITION" and r["payload"]["position_id"] == ids["good"]
    )
    good.update(expiry_date=None, minimum_remaining_days=30)
    query = catalog().resolve("STOCK_SUMMARY").handler.normalize(parameters("STOCK_SUMMARY", ids))
    rows, _ = calculate("STOCK_SUMMARY", records, query)
    row = next(r for r in rows if r["item_id"] == ids["item"] and r["owner"] == "OWN")
    assert row["quantity"] == "70.0000" and row["carrying_value"] == "700.0000"
    assert row["eligible"] == row["available"] == "0.0000"


def test_final_review_expiry_lists_missing_dates_required_for_minimum_life():
    records, ids = inventory_records()
    bulk = next(
        r["payload"]
        for r in records
        if r["payload"]["kind"] == "POSITION" and r["payload"]["position_id"] == ids["bulk"]
    )
    bulk["minimum_remaining_days"] = 30
    query = catalog().resolve("STOCK_EXPIRY").handler.normalize(parameters("STOCK_EXPIRY", ids))
    rows, _ = calculate("STOCK_EXPIRY", records, query)
    row = next(r for r in rows if r["position_id"] == ids["bulk"])
    assert row["status"] == "UNKNOWN_EXPIRY"
    assert row["quantity"] == "2"


@pytest.mark.parametrize("link", ["stock_item_entries", "stock_group_items"])
def test_final_review_inventory_drilldowns_preserve_parent_scope(link):
    from reports.domain.reporting.drilldowns import parameters_for

    _, ids = inventory_records()
    parent = {
        "as_of": "2026-04-30",
        "location_id": ids["location"],
        "include_inactive": False,
        "owner": "OWN",
        "group_id": ids["group"],
    }
    row = {"item_id": ids["item"], "group_id": ids["group"], "owner": "OWN"}
    child = parameters_for(link, parent, row, "2026-04-01")
    assert child["location_id"] == parent["location_id"]
    assert child["include_inactive"] is False
    assert child["owner"] == "OWN"
    assert child["group_id"] == ids["group"]


def test_final_review_ageing_refuses_duplicate_origin_identity():
    records, ids = inventory_records()
    good = next(
        r["payload"]
        for r in records
        if r["payload"]["kind"] == "POSITION" and r["payload"]["position_id"] == ids["good"]
    )
    origin = good["origins"][0]
    good["origins"] = [
        origin | {"quantity": "20"},
        origin | {"quantity": "40", "receipt_date": "2026-04-15"},
    ]
    query = catalog().resolve("STOCK_AGEING").handler.normalize(parameters("STOCK_AGEING", ids))
    with pytest.raises(ValueError, match="duplicate receipt origin"):
        calculate("STOCK_AGEING", records, query)


def test_final_review_group_drilldown_cannot_replace_parent_group_with_overlapping_group():
    from reports.domain.reporting.drilldowns import parameters_for

    _, ids = inventory_records()
    # A child-group filtered report still contains ancestor rollups. Selecting that
    # ancestor must not include its other children in the detail run.
    parent = {"as_of": "2026-04-30", "group_id": ids["child"]}
    row = {"group_id": ids["group"], "owner": "OWN"}
    assert parameters_for("stock_group_items", parent, row, None) is None


def test_valuation_controls_and_filtered_scope_do_not_claim_company_reconciliation():
    (rows, evidence), ids = run("STOCK_VALUATION")
    control = next(r for r in rows if r["row_kind"] == "GL_CONTROL")
    assert control["carrying_value"] == "720.0000" and control["difference"] == "0.0000"
    assert len([r for r in rows if r["row_kind"] == "POSITION"]) == 3
    records, ids = inventory_records()
    query = (
        catalog()
        .resolve("STOCK_VALUATION")
        .handler.normalize(
            {
                "as_of": "2026-04-30",
                "item_id": ids["item"],
            }
        )
    )
    rows, evidence = calculate("STOCK_VALUATION", records, query)
    assert not any(r["row_kind"] == "GL_CONTROL" for r in rows)
    assert evidence["scope"] == "FILTERED"


def test_group_ancestors_deduplicate_leaf_membership_and_separate_units():
    (rows, _), ids = run("STOCK_GROUP_SUMMARY")
    own = [r for r in rows if r["group_id"] == ids["group"] and r["owner"] == "OWN"]
    assert {(r["unit"], r["quantity"]) for r in own} == {("PCS", "70.0000"), ("KG", "2.0000")}


def test_expiry_and_ageing_have_distinct_date_boundaries():
    (rows, _), _ = run("STOCK_EXPIRY", days_ahead=30)
    assert {r["status"] for r in rows} == {"EXPIRED", "NEAR_EXPIRY"}
    (rows, _), _ = run("STOCK_AGEING", buckets=[29, 30])
    assert all(r["age_days"] == 29 and r["age_bucket"] == "29-29" for r in rows)
    assert sum(Decimal(r["quantity"]) for r in rows) == Decimal(77)


def test_reorder_uses_eligible_unreserved_not_physical_stock():
    (rows, _), ids = run("STOCK_REORDER")
    item = next(r for r in rows if r["item_id"] == ids["item"])
    assert item["shortage"] == "25.0000" and item["suggested_quantity"] == "45.0000"
    assert item["orders_status"] == "NOT_INCLUDED"
    with pytest.raises(ValueError, match="order supply/demand"):
        run("STOCK_REORDER", include_orders=True)


@pytest.mark.parametrize(
    "capability,code",
    [
        ("valuation_complete", "STOCK_VALUATION"),
        ("origins_complete", "STOCK_AGEING"),
        ("movements_complete", "ITEM_LEDGER"),
        ("reservations_complete", "STOCK_REORDER"),
    ],
)
def test_dependent_reports_refuse_incomplete_capabilities(capability, code):
    records, ids = inventory_records()
    records[0]["payload"][capability] = False
    with pytest.raises(ValueError, match="unavailable|requires"):
        calculate(code, records, catalog().resolve(code).handler.normalize(parameters(code, ids)))


def test_missing_reservations_are_null_not_available_zero_and_missing_origins_are_unknown():
    records, ids = inventory_records()
    records[0]["payload"]["reservations_complete"] = False
    query = catalog().resolve("STOCK_SUMMARY").handler.normalize(parameters("STOCK_SUMMARY", ids))
    rows, _ = calculate("STOCK_SUMMARY", records, query)
    assert all(row["available"] is None and row["reserved"] is None for row in rows)
    for record in records:
        if record["payload"]["kind"] == "POSITION":
            record["payload"]["origins"][0].update(receipt_date=None, provenance="UNKNOWN")
    query = catalog().resolve("STOCK_AGEING").handler.normalize(parameters("STOCK_AGEING", ids))
    rows, _ = calculate("STOCK_AGEING", records, query)
    assert all(row["age_bucket"] == "UNKNOWN" for row in rows)


@pytest.mark.parametrize("mutation", ["count", "reference", "duplicate", "cycle", "quantity"])
def test_corrupt_stock_source_never_produces_plausible_balances(mutation):
    records, ids = inventory_records()
    if mutation == "count":
        records[0]["payload"]["position_count"] += 1
    elif mutation == "reference":
        next(r["payload"] for r in records if r["payload"]["kind"] == "POSITION")["item_id"] = str(
            uuid.uuid4()
        )
    elif mutation == "duplicate":
        records.append(deepcopy(records[1]))
    elif mutation == "cycle":
        next(r["payload"] for r in records if r["payload"]["kind"] == "GROUP")["parent_id"] = ids[
            "child"
        ]
    else:
        next(r["payload"] for r in records if r["payload"]["kind"] == "MOVEMENT")[
            "quantity_delta"
        ] = "101"
    with pytest.raises(ValueError):
        calculate("STOCK_SUMMARY", records, {"as_of": "2026-04-30"})


def test_frozen_asof_scope_and_unsupported_inputs_fail_closed():
    with pytest.raises(ValueError, match="matching frozen"):
        run("STOCK_SUMMARY", as_of="2026-04-29")
    with pytest.raises(ValueError, match="outside the frozen"):
        run("STOCK_SUMMARY", location_id=str(uuid.uuid4()))
    with pytest.raises(ValueError, match="predates"):
        run("ITEM_LEDGER", date_from="2026-03-01")
    assert dt.date(2026, 4, 30).isoformat() == "2026-04-30"


def test_review_zero_stock_item_is_visible_and_can_require_reordering():
    records, ids = inventory_records()
    empty = deepcopy(records[1])
    empty["payload"].update(item_id=str(uuid.uuid4()), code="EMPTY", name="Empty item")
    records.append(empty)
    records[0]["payload"]["item_count"] += 1
    query = catalog().resolve("STOCK_REORDER").handler.normalize({"as_of": "2026-04-30"})
    rows, _ = calculate("STOCK_REORDER", records, query)
    row = next(r for r in rows if r["item_code"] == "EMPTY")
    assert row["quantity"] == "0.0000" and row["suggested_quantity"] == "100.0000"


def test_review_duplicate_position_grain_and_isolated_group_cycle_are_rejected():
    records, ids = inventory_records()
    duplicate = deepcopy(next(r for r in records if r["payload"]["kind"] == "POSITION"))
    duplicate["payload"]["position_id"] = str(uuid.uuid4())
    records.append(duplicate)
    records[0]["payload"]["position_count"] += 1
    records[0]["payload"]["movements_complete"] = False
    with pytest.raises(ValueError, match="position grain"):
        calculate("STOCK_SUMMARY", records, {"as_of": "2026-04-30"})
    records, ids = inventory_records()
    orphan = str(uuid.uuid4())
    records.append(
        {
            "payload": {
                "kind": "GROUP",
                "group_id": orphan,
                "code": "ORPHAN",
                "name": "Orphan",
                "parent_id": orphan,
            }
        }
    )
    records[0]["payload"]["group_count"] += 1
    with pytest.raises(ValueError, match="cyclic"):
        calculate("STOCK_GROUP_SUMMARY", records, {"as_of": "2026-04-30"})


def test_review_group_filter_does_not_claim_complete_company_and_transfer_is_not_consumption():
    records, ids = inventory_records()
    query = (
        catalog()
        .resolve("STOCK_MOVEMENT")
        .handler.normalize(
            {
                "as_of": "2026-04-30",
                "date_from": "2026-04-01",
                "nonmoving_days": 20,
            }
        )
    )
    sale = next(r["payload"] for r in records if r["payload"].get("action") == "SALE")
    sale.update(action="TRANSFER_OUT", transfer_id=str(uuid.uuid4()))
    rows, _ = calculate("STOCK_MOVEMENT", records, query)
    row = next(r for r in rows if r["item_id"] == ids["item"] and r["owner"] == "OWN")
    assert row["sales"] == "0.0000" and row["transfer_out"] == "40.0000"
    assert row["last_consumption_date"] is None and row["nonmoving"] is True


def test_legacy_financial_feed_remains_compatible_but_cannot_claim_stock_grains():
    from fixtures import dataset, manifest
    from reporting_contract.contract import LEGACY_SCHEMA_HASH, Manifest

    value = manifest(dataset()).model_dump(mode="json")
    value["schema_hash"] = LEGACY_SCHEMA_HASH
    value["control"]["counts"].pop("inventory_report_record", None)
    assert Manifest.model_validate(value).schema_hash == LEGACY_SCHEMA_HASH
    value["control"]["counts"]["inventory_report_record"] = 1
    with pytest.raises(ValidationError, match="legacy financial schema"):
        Manifest.model_validate(value)


@pytest.mark.parametrize(
    "case",
    [
        "missing_coverage",
        "movement_count",
        "missing_lot",
        "missing_reservation",
        "missing_value",
        "origin_quantity",
        "future_origin",
        "movement_dimension",
        "movement_date",
        "movement_sequence",
        "negative_history",
        "movement_value",
        "missing_mapping",
        "missing_gl",
    ],
)
def test_incomplete_or_inconsistent_owner_evidence_is_refused(case):
    records, ids = inventory_records()
    coverage = records[0]["payload"]
    positions = [r["payload"] for r in records if r["payload"]["kind"] == "POSITION"]
    good = next(p for p in positions if p["position_id"] == ids["good"])
    moves = [r["payload"] for r in records if r["payload"]["kind"] == "MOVEMENT"]
    sale = next(m for m in moves if m["action"] == "SALE")
    code = "STOCK_VALUATION" if case in {"missing_mapping", "missing_gl"} else "STOCK_SUMMARY"
    if case == "missing_coverage":
        records = records[1:]
    elif case == "movement_count":
        coverage["movement_count"] += 1
    elif case == "missing_lot":
        good.update(lot_id=None, lot_code=None)
    elif case == "missing_reservation":
        good["reserved"] = None
    elif case == "missing_value":
        good["carrying_value"] = None
    elif case == "origin_quantity":
        good["origins"][0]["quantity"] = "61"
    elif case == "future_origin":
        good["origins"][0]["receipt_date"] = "2027-01-01"
    elif case == "movement_dimension":
        sale["location_id"] = str(uuid.uuid4())
    elif case == "movement_date":
        sale["effective_date"] = "2027-01-01"
    elif case == "movement_sequence":
        extra = deepcopy(
            next(m for m in moves if m["position_id"] == ids["good"] and m["action"] == "OPENING")
        )
        extra["movement_id"] = str(uuid.uuid4())
        records.append({"payload": extra})
        coverage["movement_count"] += 1
    elif case == "negative_history":
        coverage["history_start"] = "2026-03-01"
        sale["effective_date"] = "2026-03-02"
    elif case == "movement_value":
        sale["value_delta"] = "-401"
    elif case == "missing_mapping":
        good["control_account_id"] = None
    else:
        records = [r for r in records if r["payload"]["kind"] != "GL_CONTROL"]
    query = catalog().resolve(code).handler.normalize(parameters(code, ids))
    with pytest.raises(ValueError):
        calculate(code, records, query)


def test_serial_count_and_duplicate_physical_unit_identifiers_are_validated():
    records, ids = inventory_records()
    kg = next(
        r["payload"]
        for r in records
        if r["payload"]["kind"] == "ITEM" and r["payload"]["item_id"] == ids["kg"]
    )
    bulk = next(
        r["payload"]
        for r in records
        if r["payload"].get("position_id") == ids["bulk"] and r["payload"]["kind"] == "POSITION"
    )
    kg["serial_tracked"] = True
    bulk["serials"] = ["A", "B"]
    query = catalog().resolve("BATCH_SUMMARY").handler.normalize(parameters("BATCH_SUMMARY", ids))
    rows, _ = calculate("BATCH_SUMMARY", records, query)
    assert next(r for r in rows if r["item_id"] == ids["kg"])["serial_count"] == 2
    bulk["serials"] = ["A"]
    with pytest.raises(ValueError, match="whole-unit"):
        calculate("BATCH_SUMMARY", records, query)
    bulk["serials"] = ["A", "B"]
    third = next(
        r["payload"]
        for r in records
        if r["payload"].get("position_id") == ids["third"] and r["payload"]["kind"] == "POSITION"
    )
    third.update(item_id=ids["kg"], lot_id=None, lot_code=None, serials=["A", "C", "D", "E", "F"])
    with pytest.raises(ValueError, match="multiple positions"):
        calculate("BATCH_SUMMARY", records, query)


@pytest.mark.parametrize("change", ["minimum_life", "transit", "expiry_day"])
def test_eligibility_exclusions_do_not_remove_physical_quantity_or_value(change):
    records, ids = inventory_records()
    good = next(
        r["payload"]
        for r in records
        if r["payload"].get("position_id") == ids["good"] and r["payload"]["kind"] == "POSITION"
    )
    if change == "minimum_life":
        good["minimum_remaining_days"] = 30
    elif change == "transit":
        good["custody"] = "TRANSIT"
    else:
        good["expiry_date"] = "2026-04-30"
    query = catalog().resolve("STOCK_SUMMARY").handler.normalize(parameters("STOCK_SUMMARY", ids))
    rows, _ = calculate("STOCK_SUMMARY", records, query)
    own = [r for r in rows if r["item_id"] == ids["item"] and r["owner"] == "OWN"]
    assert sum(Decimal(r["quantity"]) for r in own) == 70
    assert sum(Decimal(r["carrying_value"]) for r in own) == 700
    assert all(r["available"] == "0.0000" for r in own)


def test_expiry_unknown_window_exclusion_and_manufacture_ageing():
    records, ids = inventory_records()
    entry = catalog().resolve("STOCK_EXPIRY")
    rows, _ = calculate(
        "STOCK_EXPIRY",
        records,
        entry.handler.normalize(
            {
                "as_of": "2026-04-30",
                "days_ahead": 0,
                "include_expired": False,
            }
        ),
    )
    assert rows == []
    good = next(
        r["payload"]
        for r in records
        if r["payload"].get("position_id") == ids["good"] and r["payload"]["kind"] == "POSITION"
    )
    good["expiry_date"] = None
    rows, _ = calculate("STOCK_EXPIRY", records, entry.handler.normalize({"as_of": "2026-04-30"}))
    assert any(r["status"] == "UNKNOWN_EXPIRY" for r in rows)
    for record in records:
        if record["payload"]["kind"] == "POSITION":
            for origin in record["payload"]["origins"]:
                origin["manufacture_date"] = "2026-02-01"
    rows, _ = calculate(
        "STOCK_AGEING",
        records,
        catalog()
        .resolve("STOCK_AGEING")
        .handler.normalize(
            {
                "as_of": "2026-04-30",
                "age_basis": "MANUFACTURE",
                "buckets": [30, 60],
            }
        ),
    )
    assert all(r["age_bucket"] == "60+" and r["age_basis"] == "MANUFACTURE" for r in rows)


def test_reorder_order_capability_scope_and_deduplicated_available_demand():
    records, ids = inventory_records()
    records[0]["payload"]["orders_complete"] = True
    entry = catalog().resolve("STOCK_REORDER")
    query = entry.handler.normalize({"as_of": "2026-04-30", "include_orders": True})
    with pytest.raises(ValueError, match="item order coverage"):
        calculate("STOCK_REORDER", records, query)
    for record in records:
        if record["payload"]["kind"] == "ITEM":
            record["payload"].update(pending_supply="30", pending_demand="10")
    rows, _ = calculate("STOCK_REORDER", records, query)
    row = next(r for r in rows if r["item_id"] == ids["item"])
    assert row["projected_available"] == "75.0000" and row["suggested_quantity"] == "25.0000"
    with pytest.raises(ValueError, match="location-specific"):
        calculate("STOCK_REORDER", records, query | {"location_id": ids["location"]})
    for record in records:
        if record["payload"]["kind"] == "ITEM":
            record["payload"].update(pending_supply="1000")
    assert calculate("STOCK_REORDER", records, query)[0] == []
    for record in records:
        if record["payload"]["kind"] == "ITEM":
            record["payload"].update(reorder_level=None, target_level=None)
    assert calculate("STOCK_REORDER", records, query)[0] == []


def test_owner_and_inactive_filters_and_nonmoving_window_preserve_scope():
    records, ids = inventory_records()
    for record in records:
        if record["payload"]["kind"] == "ITEM" and record["payload"]["item_id"] == ids["kg"]:
            record["payload"]["active"] = False
    query = (
        catalog()
        .resolve("STOCK_SUMMARY")
        .handler.normalize(
            {
                "as_of": "2026-04-30",
                "owner": "THIRD_PARTY",
                "include_inactive": False,
                "location_id": ids["location"],
                "group_id": ids["group"],
            }
        )
    )
    rows, evidence = calculate("STOCK_SUMMARY", records, query)
    assert len(rows) == 1 and rows[0]["owner"] == "THIRD_PARTY"
    assert evidence["scope"] == "FILTERED"
    rows, _ = calculate(
        "STOCK_MOVEMENT",
        records,
        catalog()
        .resolve("STOCK_MOVEMENT")
        .handler.normalize(
            {
                "as_of": "2026-04-30",
                "date_from": "2026-04-01",
                "nonmoving_days": 90,
                "only_nonmoving": True,
            }
        ),
    )
    assert rows == []


def test_batch_trace_and_exited_serial_history_keep_balance_and_movement_grains_separate():
    records, ids = inventory_records()
    entry = catalog().resolve("BATCH_SUMMARY")
    query = entry.handler.normalize({"as_of": "2026-04-30", "include_history": True})
    rows, _ = calculate("BATCH_SUMMARY", records, query)
    assert any(row["row_kind"] == "BATCH_POSITION" for row in rows)
    assert any(
        row["row_kind"] == "BATCH_MOVEMENT" and row["voucher_number"] == "SALE-1" for row in rows
    )
    assert all("quantity" not in row for row in rows if row["row_kind"] == "BATCH_MOVEMENT")
    for record in records:
        payload = record["payload"]
        if payload["kind"] == "ITEM" and payload["item_id"] == ids["item"]:
            payload["serial_tracked"] = True
        if payload["kind"] == "POSITION" and payload["item_id"] == ids["item"]:
            prefix = {ids["good"]: "UNIT", ids["held"]: "HELD", ids["third"]: "THIRD"}[
                payload["position_id"]
            ]
            payload["serials"] = [f"{prefix}-{i}" for i in range(1, int(payload["quantity"]) + 1)]
        if payload["kind"] == "MOVEMENT" and payload["item_id"] == ids["item"]:
            prefix = {ids["good"]: "UNIT", ids["held"]: "HELD", ids["third"]: "THIRD"}[
                payload["position_id"]
            ]
            start = 61 if payload["action"] == "SALE" else 1
            payload["serials"] = [
                f"{prefix}-{i}" for i in range(start, start + abs(int(payload["quantity_delta"])))
            ]
    query = entry.handler.normalize(
        {
            "as_of": "2026-04-30",
            "include_history": True,
            "serial": "unit-99",
        }
    )
    with pytest.raises(ValueError, match="serial movement history"):
        calculate("BATCH_SUMMARY", records, query)
    records[0]["payload"]["serial_history_complete"] = True
    rows, _ = calculate("BATCH_SUMMARY", records, query)
    assert len(rows) == 2 and all(row["row_kind"] == "BATCH_MOVEMENT" for row in rows)
    assert [row["movement_quantity"] for row in rows] == ["1.0000", "-1.0000"]
    assert [row["source_movement_quantity"] for row in rows] == ["100", "-40"]
    assert all(row["serials"] == "UNIT-99" for row in rows)
    current, _ = calculate("BATCH_SUMMARY", records, query | {"serial": "unit-50"})
    position = next(row for row in current if row["row_kind"] == "BATCH_POSITION")
    assert position["quantity"] == "1.0000" and position["source_position_quantity"] == "60"
    assert position["serial"] == "UNIT-50" and position["serial_count"] == 1
    sale = next(r["payload"] for r in records if r["payload"].get("action") == "SALE")
    original_sale = list(sale["serials"])
    sale["serials"][-1] = "NEVER-RECEIVED"
    with pytest.raises(ValueError, match="retained unit state"):
        calculate("BATCH_SUMMARY", records, query)
    sale["serials"] = original_sale
    good = next(
        r["payload"]
        for r in records
        if r["payload"]["kind"] == "POSITION" and r["payload"]["position_id"] == ids["good"]
    )
    good["serials"][-1] = "REASSIGNED"
    with pytest.raises(ValueError, match="current positions"):
        calculate("BATCH_SUMMARY", records, query)
    good["serials"][-1] = "UNIT-60"
    held = next(
        r["payload"]
        for r in records
        if r["payload"]["kind"] == "POSITION" and r["payload"]["position_id"] == ids["held"]
    )
    held_move = next(
        r["payload"]
        for r in records
        if r["payload"]["kind"] == "MOVEMENT" and r["payload"]["position_id"] == ids["held"]
    )
    held["serials"][0] = held_move["serials"][0] = "UNIT-99"
    with pytest.raises(ValueError, match="already-held"):
        calculate("BATCH_SUMMARY", records, query)
    held["serials"][0] = held_move["serials"][0] = "HELD-1"
    assert calculate("BATCH_SUMMARY", records, query | {"serial": "UNKNOWN"})[0] == []
    records[0]["payload"]["movements_complete"] = False
    with pytest.raises(ValueError, match="retained stock movement history"):
        calculate("BATCH_SUMMARY", records, query)
    records[0]["payload"]["movements_complete"] = True
    sale["serials"] = sale["serials"][:-1]
    with pytest.raises(ValueError, match="identities do not reconcile"):
        calculate("BATCH_SUMMARY", records, query)
    with pytest.raises(ValidationError, match="requires include_history"):
        entry.handler.normalize({"as_of": "2026-04-30", "serial": "UNIT-99"})
