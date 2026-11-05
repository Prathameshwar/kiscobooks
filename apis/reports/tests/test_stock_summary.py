"""Full-result stock totals and search never aggregate incompatible units."""

from inventory_fixture import inventory_records

from reports.domain.reporting.inventory import calculate


def test_stock_summary_reconciles_opening_receipts_issues_value_and_reservations():
    from copy import deepcopy

    records, ids = inventory_records()
    records = [
        row
        for row in records
        if row["payload"]["kind"] in {"COVERAGE", "LOCATION", "GROUP", "GL_CONTROL"}
        or (
            row["payload"].get("item_id") == ids["item"]
            and row["payload"].get("position_id", ids["good"]) == ids["good"]
        )
    ]
    coverage = next(row["payload"] for row in records if row["payload"]["kind"] == "COVERAGE")
    coverage.update(item_count=1, position_count=1, movement_count=3)
    position = next(row["payload"] for row in records if row["payload"]["kind"] == "POSITION")
    position.update(
        quantity="115",
        opening_quantity="100",
        inward_quantity="40",
        outward_quantity="25",
        carrying_value="1437.5000",
        reserved="5",
    )
    position["origins"][0]["quantity"] = "115"
    movements = [row["payload"] for row in records if row["payload"]["kind"] == "MOVEMENT"]
    movements[0]["value_delta"] = "1250"
    movements[1].update(action="RECEIPT", quantity_delta="40", value_delta="500")
    issue = deepcopy(movements[1])
    issue.update(
        movement_id=ids["held"],
        sequence=3,
        effective_date="2026-04-20",
        action="SALE",
        voucher_number="SALE-2",
        quantity_delta="-25",
        value_delta="-312.5000",
    )
    records.append({"payload": issue})
    next(row["payload"] for row in records if row["payload"]["kind"] == "GL_CONTROL")["balance"] = (
        "1437.5000"
    )

    rows, evidence = calculate("STOCK_SUMMARY", records, {"as_of": "2026-04-30"})
    assert len(rows) == 1
    assert {key: rows[0][key] for key in ("opening", "inward", "outward", "quantity")} == {
        "opening": "100.0000",
        "inward": "40.0000",
        "outward": "25.0000",
        "quantity": "115.0000",
    }
    assert rows[0]["available"] == "110.0000"
    assert rows[0]["carrying_value"] == "1437.5000"
    assert evidence["stock_summary"]["owned_value"] == "1437.5000"
    ledger, _ = calculate(
        "ITEM_LEDGER",
        records,
        {"as_of": "2026-04-30", "date_from": "2026-04-01", "item_id": ids["item"]},
    )
    assert ledger[-1]["balance"] == rows[0]["quantity"]


def test_stock_summary_totals_are_full_selection_and_separated_by_unit_owner_custody():
    records, _ = inventory_records()
    rows, evidence = calculate("STOCK_SUMMARY", records, {"as_of": "2026-04-30"})
    summary = evidence["stock_summary"]
    assert summary["item_count"] == 2
    assert summary["row_count"] == len(rows)
    assert {r["unit"] for r in summary["quantities"]} == {"PCS", "KG"}
    owned = next(r for r in summary["quantities"] if r["unit"] == "PCS" and r["owner"] == "OWN")
    assert owned["quantity"] == "70.0000"
    assert owned["eligible"] == "60.0000"
    assert owned["available"] == "55.0000"
    assert summary["owned_value"] == "720.0000"


def test_stock_summary_search_is_case_insensitive_and_applied_before_totals():
    records, _ = inventory_records()
    rows, evidence = calculate("STOCK_SUMMARY", records, {"as_of": "2026-04-30", "search": "kG"})
    assert len(rows) == 1 and rows[0]["unit"] == "KG"
    assert evidence["stock_summary"]["item_count"] == 1
    assert evidence["stock_summary"]["owned_value"] == "20.0000"


async def test_frozen_choices_verify_coverage_and_recheck_permissions(app, client):
    import uuid

    from conftest import COMPANY, PERMISSIONS, headers
    from inventory_fixture import inventory_dataset
    from test_native_ledger import prepared

    facts, ids = inventory_dataset()
    identities, _, _ = await prepared(app, dataset=(facts, ids))
    path = f"/v2/companies/{COMPANY}/report-generations/{identities[2]}/inventory"
    result = await client.get(path, headers=headers(), params={"kind": "ITEM", "q": "kG"})
    assert result.status_code == 200, result.text
    assert result.json()["coverage"]["as_of"] == "2026-04-30"
    assert len(result.json()["items"]) == 1
    assert result.json()["items"][0]["code"] == "KG"
    assert (
        await client.get(path, headers=headers(permissions=PERMISSIONS - {"item.read"}))
    ).status_code == 403
    assert (await client.get(path, headers=headers(tenant=uuid.uuid4()))).status_code == 404
    result = await client.get(path, headers=headers(), params={"q": "%"})
    assert result.json()["items"] == []


def test_stock_summary_custody_selection_does_not_add_local_zero_rows():
    records, _ = inventory_records()
    rows, evidence = calculate(
        "STOCK_SUMMARY", records, {"as_of": "2026-04-30", "custody": "TRANSIT"}
    )
    assert rows == []
    assert evidence["stock_summary"]["item_count"] == 0


def test_stock_warehouse_and_ledger_drills_keep_row_custody_and_owner():
    from reports.domain.reporting.drilldowns import parameters_for

    row = {"item_id": "01990000-0000-7000-8000-000000000010", "owner": "OWN", "custody": "TRANSIT"}
    for key in ("stock_item_entries", "stock_item_locations"):
        filters = parameters_for(key, {"as_of": "2026-04-30"}, row, "2026-04-01")
        assert filters["owner"] == "OWN" and filters["custody"] == "TRANSIT"


def test_held_serial_quantity_is_physical_but_not_eligible_stock():
    records, ids = inventory_records()
    position = next(
        r["payload"]
        for r in records
        if r["payload"].get("position_id") == ids["good"] and r["payload"]["kind"] == "POSITION"
    )
    position["eligible_quantity"] = "59"
    _, evidence = calculate("STOCK_SUMMARY", records, {"as_of": "2026-04-30"})
    owned = next(
        r
        for r in evidence["stock_summary"]["quantities"]
        if r["unit"] == "PCS" and r["owner"] == "OWN"
    )
    assert owned["quantity"] == "70.0000"
    assert owned["eligible"] == "59.0000"
    assert owned["available"] == "54.0000"


def test_previous_committed_inventory_schema_is_still_readable():
    from fixtures import manifest
    from inventory_fixture import inventory_dataset
    from reporting_contract.contract import Manifest

    facts, _ = inventory_dataset()
    value = manifest(facts).model_dump(mode="json")
    value["schema_hash"] = "0b4102b8f825729efa319038fc30b53cb0156f3ed8783b90c32b2acda6654988"
    assert Manifest.model_validate(value).schema_hash == value["schema_hash"]


def test_excluding_zero_stock_labels_the_result_filtered():
    records, _ = inventory_records()
    _, evidence = calculate(
        "STOCK_SUMMARY", records, {"as_of": "2026-04-30", "include_zero": False}
    )
    assert evidence["scope"] == "FILTERED"


def test_changed_native_stock_cannot_certify_new_report_results():
    import pytest

    records, _ = inventory_records()
    next(r["payload"] for r in records if r["payload"]["kind"] == "COVERAGE")[
        "native_stock_current"
    ] = False
    with pytest.raises(ValueError, match="changed"):
        calculate("STOCK_SUMMARY", records, {"as_of": "2026-04-30"})


def test_stock_summary_preserves_the_catalogs_full_unit_code():
    records, _ = inventory_records()
    item = next(r["payload"] for r in records if r["payload"]["kind"] == "ITEM")
    item["unit"] = "CATALOG-BASE-UNIT-123456789012"
    rows, evidence = calculate("STOCK_SUMMARY", records, {"as_of": "2026-04-30"})
    assert any(row["unit"] == item["unit"] for row in rows)
    assert any(row["unit"] == item["unit"] for row in evidence["stock_summary"]["quantities"])


def test_distinct_bins_remain_distinct_positions_in_one_warehouse():
    import uuid

    records, ids = inventory_records()
    positions = {
        r["payload"]["position_id"]: r["payload"]
        for r in records
        if r["payload"]["kind"] == "POSITION"
    }
    positions[ids["good"]]["bin_id"] = str(uuid.uuid4())
    other = positions[ids["held"]]
    other.update(bin_id=str(uuid.uuid4()), disposition="GOOD", lot_id=ids["lot"], lot_code="LOT")
    rows, _ = calculate("STOCK_SUMMARY", records, {"as_of": "2026-04-30"}, movements_loaded=False)
    assert (
        next(row for row in rows if row["owner"] == "OWN" and row["unit"] == "PCS")["quantity"]
        == "70.0000"
    )
