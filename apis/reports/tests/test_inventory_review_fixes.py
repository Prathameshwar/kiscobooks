"""Regression cases for the inventory report contract review."""

import uuid
from copy import deepcopy
from decimal import Decimal

import pytest
from inventory_fixture import inventory_records, parameters
from pydantic import ValidationError

from reports.domain.reporting.drilldowns import parameters_for
from reports.domain.reporting.inventory import calculate
from reports.tasks.report_catalog import catalog


def query(code, ids, **overrides):
    return catalog().resolve(code).handler.normalize(parameters(code, ids) | overrides)


def cost_records():
    records, ids = inventory_records()
    return attach_cost_details(records, ids)


def attach_cost_details(records, ids):
    for record in records:
        p = record["payload"]
        if p["kind"] != "POSITION" or p["owner"] != "OWN":
            continue
        if p["position_id"] == ids["bulk"]:
            p["costing_method"] = "MOVING_AVERAGE"
            p["valuation_detail"] = {
                "pool": {
                    "pool_id": str(uuid.uuid4()),
                    "quantity": p["quantity"],
                    "carrying_value": p["carrying_value"],
                }
            }
        else:
            p["valuation_detail"] = {
                "layers": [
                    {
                        "layer_id": str(uuid.uuid4()),
                        "origin_id": p["origins"][0]["origin_id"],
                        "receipt_date": "2026-04-01",
                        "quantity": p["quantity"],
                        "carrying_value": p["carrying_value"],
                    }
                ]
            }
    return records, ids


@pytest.mark.parametrize("start,opening", [("2026-04-05", "1000.0000"), ("2026-04-20", "600.0000")])
def test_ledger_opening_and_running_value_use_requested_period(start, opening):
    records, ids = inventory_records()
    rows, _ = calculate("ITEM_LEDGER", records, query("ITEM_LEDGER", ids, date_from=start))
    good = [r for r in rows if r["position_id"] == ids["good"]]
    assert good[0]["value_balance"] == opening
    assert good[-1]["value_balance"] == "600.0000"
    assert all(r["value_balance"] is None for r in rows if r["owner"] == "THIRD_PARTY")


def test_movement_value_turnover_includes_quantity_zero_adjustments_once():
    records, ids = inventory_records()
    good = next(r["payload"] for r in records if r["payload"].get("position_id") == ids["good"])
    good["carrying_value"] = "650"
    records.append(
        {
            "payload": {
                "kind": "MOVEMENT",
                "movement_id": str(uuid.uuid4()),
                "position_id": ids["good"],
                "item_id": ids["item"],
                "location_id": ids["location"],
                "lot_id": ids["lot"],
                "effective_date": "2026-04-20",
                "sequence": 1,
                "action": "VALUE_ADJUSTMENT",
                "voucher_id": str(uuid.uuid4()),
                "voucher_number": "COST-1",
                "quantity_delta": "0",
                "value_delta": "50",
            }
        }
    )
    records[0]["payload"]["movement_count"] += 1
    rows, _ = calculate(
        "STOCK_MOVEMENT", records, query("STOCK_MOVEMENT", ids, date_from="2026-04-05")
    )
    row = next(r for r in rows if r["item_id"] == ids["item"] and r["owner"] == "OWN")
    assert [
        row[k] for k in ("opening_value", "inward_value", "outward_value", "closing_value")
    ] == [
        "1100.0000",
        "50.0000",
        "400.0000",
        "750.0000",
    ]
    assert Decimal(row["opening_value"]) + Decimal(row["inward_value"]) - Decimal(
        row["outward_value"]
    ) == Decimal(row["closing_value"])


def test_unknown_valuation_is_null_in_ledger_and_movement():
    records, ids = inventory_records()
    records[0]["payload"]["valuation_complete"] = False
    for code in ("ITEM_LEDGER", "STOCK_MOVEMENT"):
        rows, _ = calculate(code, records, query(code, ids))
        keys = (
            ("value_balance", "value_delta")
            if code == "ITEM_LEDGER"
            else (
                "opening_value",
                "inward_value",
                "outward_value",
                "closing_value",
            )
        )
        assert all(r[k] is None for r in rows for k in keys)


def test_expiry_exposes_value_reservations_and_unknown_capabilities():
    records, ids = inventory_records()
    rows, _ = calculate("STOCK_EXPIRY", records, query("STOCK_EXPIRY", ids))
    good = next(r for r in rows if r["position_id"] == ids["good"])
    assert good["carrying_value"] == "600.0000"
    assert good["reserved"] == "5.0000"
    assert good["valuation_status"] == good["reservation_status"] == "COMPLETE"
    assert next(r for r in rows if r["owner"] == "THIRD_PARTY")["carrying_value"] is None
    records[0]["payload"].update(valuation_complete=False, reservations_complete=False)
    rows, _ = calculate("STOCK_EXPIRY", records, query("STOCK_EXPIRY", ids))
    assert all(r["carrying_value"] is None and r["reserved"] is None for r in rows)
    assert all(r["valuation_status"] == r["reservation_status"] == "UNAVAILABLE" for r in rows)


def test_batch_lot_filter_applies_to_positions_history_and_drilldowns():
    records, ids = inventory_records()
    p = query("BATCH_SUMMARY", ids, lot_id=ids["lot"], include_history=True)
    rows, evidence = calculate("BATCH_SUMMARY", records, p)
    assert rows and all(r["lot_id"] == ids["lot"] for r in rows)
    assert {r["row_kind"] for r in rows} == {"BATCH_POSITION", "BATCH_MOVEMENT"}
    assert evidence["scope"] == "FILTERED"
    child = parameters_for("stock_item_entries", p, rows[0], "2026-04-01")
    assert child["lot_id"] == ids["lot"]
    assert calculate("BATCH_SUMMARY", records, p | {"lot_id": str(uuid.uuid4())})[0] == []


def test_valuation_cost_detail_is_owner_evidence_with_distinct_grains():
    records, ids = cost_records()
    rows, _ = calculate(
        "STOCK_VALUATION", records, query("STOCK_VALUATION", ids, include_cost_details=True)
    )
    layers = [r for r in rows if r["row_kind"] == "COST_LAYER"]
    pools = [r for r in rows if r["row_kind"] == "COST_POOL"]
    assert len(layers) == 2 and len(pools) == 1
    assert sum(Decimal(r["remaining_value"]) for r in layers + pools) == Decimal(720)
    assert all("quantity" not in r and "carrying_value" not in r for r in layers + pools)
    assert all(
        r["valuation_detail_status"] == "COMPLETE" for r in rows if r["row_kind"] == "POSITION"
    )
    assert (rows, _) == calculate(
        "STOCK_VALUATION",
        list(reversed(records)),
        query("STOCK_VALUATION", ids, include_cost_details=True),
    )


@pytest.mark.parametrize("mutation", ["quantity", "value", "duplicate", "method", "future"])
def test_valuation_cost_detail_must_reconcile(mutation):
    records, ids = cost_records()
    good = next(r["payload"] for r in records if r["payload"].get("position_id") == ids["good"])
    layer = good["valuation_detail"]["layers"][0]
    if mutation == "quantity":
        layer["quantity"] = "59"
    elif mutation == "value":
        layer["carrying_value"] = "599"
    elif mutation == "duplicate":
        good["valuation_detail"]["layers"].append(deepcopy(layer))
    elif mutation == "method":
        good["costing_method"] = "MOVING_AVERAGE"
    else:
        layer["receipt_date"] = "2026-05-01"
    p = query("STOCK_VALUATION", ids, include_cost_details=True)
    with pytest.raises(ValueError, match="cost|valuation|layer"):
        calculate("STOCK_VALUATION", records, p)


def test_missing_cost_detail_is_explicit_and_detailed_run_is_blocked():
    records, ids = inventory_records()
    rows, _ = calculate("STOCK_VALUATION", records, query("STOCK_VALUATION", ids))
    assert all(
        r["valuation_detail_status"] == "UNAVAILABLE" for r in rows if r["row_kind"] == "POSITION"
    )
    with pytest.raises(ValueError, match="cost detail"):
        calculate(
            "STOCK_VALUATION", records, query("STOCK_VALUATION", ids, include_cost_details=True)
        )


@pytest.mark.parametrize("capability", ["movements_complete", "valuation_complete"])
def test_detailed_valuation_requires_complete_capabilities(capability):
    records, ids = cost_records()
    records[0]["payload"][capability] = False
    with pytest.raises(ValueError, match="valuation|movement"):
        calculate(
            "STOCK_VALUATION", records, query("STOCK_VALUATION", ids, include_cost_details=True)
        )


def test_detailed_valuation_requires_loaded_history_and_retains_adjustment_source():
    records, ids = cost_records()
    p = query("STOCK_VALUATION", ids, include_cost_details=True)
    with pytest.raises(ValueError, match="movement history"):
        calculate("STOCK_VALUATION", records, p, movements_loaded=False)
    position = next(r["payload"] for r in records if r["payload"].get("position_id") == ids["good"])
    position["carrying_value"] = "650"
    position["valuation_detail"]["layers"][0]["carrying_value"] = "650"
    adjustment = {
        "kind": "MOVEMENT",
        "movement_id": str(uuid.uuid4()),
        "position_id": ids["good"],
        "item_id": ids["item"],
        "location_id": ids["location"],
        "lot_id": ids["lot"],
        "effective_date": "2026-04-20",
        "sequence": 1,
        "action": "VALUE_ADJUSTMENT",
        "voucher_id": str(uuid.uuid4()),
        "voucher_number": "COST-1",
        "quantity_delta": "0",
        "value_delta": "50",
    }
    records.append({"payload": adjustment})
    records[0]["payload"]["movement_count"] += 1
    rows, _ = calculate("STOCK_VALUATION", records, p)
    row = next(r for r in rows if r["row_kind"] == "VALUE_ADJUSTMENT")
    assert row["value_delta"] == "50.0000"
    assert row["voucher_id"] == adjustment["voucher_id"]
    assert row["movement_id"] == adjustment["movement_id"]
    assert "carrying_value" not in row and "quantity" not in row


def test_existing_inventory_manifest_hash_remains_supported():
    from fixtures import manifest
    from inventory_fixture import inventory_dataset
    from reporting_contract.contract import INVENTORY_V1_SCHEMA_HASH, Manifest

    facts, _ = inventory_dataset()
    value = manifest(facts).model_dump(mode="json")
    value["schema_hash"] = INVENTORY_V1_SCHEMA_HASH
    assert Manifest.model_validate(value).schema_hash == INVENTORY_V1_SCHEMA_HASH
    assert value["control"]["counts"]["inventory_report_record"] > 0


def test_new_report_columns_are_typed_in_both_views():
    for code, names in {
        "ITEM_LEDGER": {"value_balance"},
        "STOCK_MOVEMENT": {"opening_value", "inward_value", "outward_value", "closing_value"},
        "STOCK_EXPIRY": {"carrying_value", "reserved"},
        "STOCK_VALUATION": {"remaining_value", "remaining_quantity", "valuation_detail_status"},
    }.items():
        for view in catalog().resolve(code).definition.views:
            columns = {c.key: c for c in view.columns}
            assert names <= columns.keys()
            for key in names - {"reserved", "remaining_quantity", "valuation_detail_status"}:
                assert columns[key].kind == "MONEY" and columns[key].currency_key == "currency"


def test_invalid_lot_filter_remains_typed():
    _, ids = inventory_records()
    with pytest.raises(ValidationError):
        query("BATCH_SUMMARY", ids, lot_id="invalid")
