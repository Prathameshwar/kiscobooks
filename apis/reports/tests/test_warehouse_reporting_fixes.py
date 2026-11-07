"""Warehouse rollups deduplicate descendants and respect operation eligibility."""

import uuid

import pytest
from inventory_fixture import inventory_records, parameters

from reports.domain.reporting.inventory import calculate
from reports.tasks.report_catalog import catalog


def query(ids, **values):
    return (
        catalog()
        .resolve("LOCATION_STOCK")
        .handler.normalize(parameters("LOCATION_STOCK", ids) | values)
    )


def test_reporting_warehouse_group_parent_selection_counts_stock_once():
    records, ids = inventory_records()
    expected, _ = calculate("LOCATION_STOCK", records, query(ids))
    parent, child = str(uuid.uuid4()), str(uuid.uuid4())
    for row in records:
        value = row["payload"]
        if value["kind"] == "COVERAGE":
            value["location_count"] += 2
        if value["kind"] == "LOCATION":
            value["parent_id"] = child
    records.extend(
        {"payload": value}
        for value in [
            {
                "kind": "LOCATION",
                "location_id": parent,
                "code": "REGION",
                "name": "Region",
                "is_group": True,
            },
            {
                "kind": "LOCATION",
                "location_id": child,
                "code": "AREA",
                "name": "Area",
                "is_group": True,
                "parent_id": parent,
            },
        ]
    )
    actual, _ = calculate("LOCATION_STOCK", records, query(ids, location_id=parent))
    assert actual == expected


@pytest.mark.parametrize("restriction", ["warehouse", "product"])
def test_warehouse_stock_keeps_quantity_but_excludes_blocked_sale_eligibility(restriction):
    records, ids = inventory_records()
    expected, _ = calculate("LOCATION_STOCK", records, query(ids))
    for row in records:
        value = row["payload"]
        if restriction == "warehouse" and value["kind"] == "LOCATION":
            value["sale_eligible"] = False
        if restriction == "product" and value["kind"] == "ITEM":
            value["sale_location_mode"] = "ALLOW_LIST"
    actual, _ = calculate("LOCATION_STOCK", records, query(ids))
    for before, after in zip(expected, actual, strict=True):
        assert before["quantity"] == after["quantity"]
        assert before["carrying_value"] == after["carrying_value"]
        assert after["eligible"] == "0.0000"
