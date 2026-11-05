"""Small exact owner fixture: eligible/held/third-party stock and incompatible base units."""

import uuid
from copy import deepcopy

from fixtures import dataset, source


def inventory_records():
    ids = {
        key: str(uuid.uuid4())
        for key in (
            "item",
            "kg",
            "location",
            "group",
            "child",
            "account",
            "good",
            "held",
            "third",
            "bulk",
            "lot",
            "old_lot",
        )
    }
    records = [
        {
            "payload": {
                "kind": "COVERAGE",
                "as_of": "2026-04-30",
                "history_start": "2026-04-01",
                "classification_date": "2026-04-01",
                "timezone": "Asia/Kolkata",
                "currency": "INR",
                "policy_hash": "a" * 64,
                "complete_company": True,
                "item_count": 2,
                "location_count": 1,
                "group_count": 2,
                "position_count": 4,
                "movement_count": 5,
                "movements_complete": True,
                "valuation_complete": True,
                "reservations_complete": True,
                "orders_complete": False,
                "origins_complete": True,
                "gl_complete": True,
            }
        }
    ]
    for key, unit, lot in (("item", "PCS", True), ("kg", "KG", False)):
        records.append(
            {
                "payload": {
                    "kind": "ITEM",
                    "item_id": ids[key],
                    "code": key.upper(),
                    "name": key.title(),
                    "unit": unit,
                    "group_ids": [ids["group"], ids["child"]],
                    "active": True,
                    "lot_tracked": lot,
                    "serial_tracked": False,
                    "reorder_level": "80",
                    "target_level": "100",
                    "minimum_order": "10",
                }
            }
        )
    records += [
        {
            "payload": {
                "kind": "LOCATION",
                "location_id": ids["location"],
                "code": "MAIN",
                "name": "Main",
            }
        },
        {
            "payload": {
                "kind": "GROUP",
                "group_id": ids["group"],
                "code": "ALL",
                "name": "All",
            }
        },
        {
            "payload": {
                "kind": "GROUP",
                "group_id": ids["child"],
                "parent_id": ids["group"],
                "code": "CHILD",
                "name": "Child",
            }
        },
    ]
    for key, item, quantity, owner, disposition, lot, expiry in (
        ("good", "item", "60", "OWN", "GOOD", "lot", "2026-05-20"),
        ("held", "item", "10", "OWN", "HELD", "old_lot", "2026-04-20"),
        ("third", "item", "5", "THIRD_PARTY", "GOOD", "lot", "2026-05-20"),
        ("bulk", "kg", "2", "OWN", "GOOD", None, None),
    ):
        value = str(int(quantity) * 10) if owner == "OWN" else None
        origin_id = str(uuid.uuid4())
        records.append(
            {
                "payload": {
                    "kind": "POSITION",
                    "position_id": ids[key],
                    "item_id": ids[item],
                    "location_id": ids["location"],
                    "owner": owner,
                    "custody": "LOCAL",
                    "lot_id": ids[lot] if lot else None,
                    "lot_code": lot.upper() if lot else None,
                    "expiry_date": expiry,
                    "disposition": disposition,
                    "quantity": quantity,
                    "opening_quantity": "100" if key == "good" else quantity,
                    "inward_quantity": "0",
                    "outward_quantity": "40" if key == "good" else "0",
                    "reserved": "5" if key == "good" else "0",
                    "carrying_value": value,
                    "costing_method": "FIFO" if owner == "OWN" else None,
                    "control_account_id": ids["account"] if owner == "OWN" else None,
                    "origins": [
                        {
                            "origin_id": origin_id,
                            "receipt_date": "2026-04-01",
                            "provenance": "KNOWN",
                            "quantity": quantity,
                        }
                    ],
                }
            }
        )
        records.append(
            {
                "payload": {
                    "kind": "MOVEMENT",
                    "movement_id": str(uuid.uuid4()),
                    "position_id": ids[key],
                    "item_id": ids[item],
                    "location_id": ids["location"],
                    "lot_id": ids[lot] if lot else None,
                    "effective_date": "2026-04-01",
                    "sequence": {"good": 1, "held": 2, "third": 3, "bulk": 4}[key],
                    "action": "OPENING",
                    "voucher_id": str(uuid.uuid4()),
                    "voucher_number": f"OPEN-{key}",
                    "quantity_delta": "100" if key == "good" else quantity,
                    "value_delta": "1000" if key == "good" else value,
                    "origin_id": origin_id,
                }
            }
        )
        if key == "good":
            records.append(
                {
                    "payload": {
                        "kind": "MOVEMENT",
                        "movement_id": str(uuid.uuid4()),
                        "position_id": ids[key],
                        "item_id": ids[item],
                        "location_id": ids["location"],
                        "lot_id": ids[lot],
                        "effective_date": "2026-04-10",
                        "sequence": 2,
                        "action": "SALE",
                        "voucher_id": str(uuid.uuid4()),
                        "voucher_number": "SALE-1",
                        "quantity_delta": "-40",
                        "value_delta": "-400",
                        "origin_id": origin_id,
                    }
                }
            )
    records.append(
        {
            "payload": {
                "kind": "GL_CONTROL",
                "account_id": ids["account"],
                "currency": "INR",
                "balance": "720",
            }
        }
    )
    return deepcopy(records), ids


def inventory_dataset():
    records, ids = inventory_records()
    financial = dataset()
    offset = str(uuid.uuid4())
    account_fact = next(row for row in financial if row.entity == "account")
    financial.append(
        source(
            "account",
            uuid.UUID(offset),
            account_fact.data
            | {
                "code": "OFFSET",
                "name": "Offset",
                "kind": "GENERAL",
            },
        )
    )
    financial = [
        source(row.entity, row.source_id, row.data | {"account_id": offset})
        if row.entity == "journal_line" and row.data["side"] == "CREDIT"
        else row
        for row in financial
    ]
    account = next(
        row.source_id
        for row in financial
        if row.entity == "journal_line" and row.data["side"] == "DEBIT"
    )
    account_id = next(
        row.data["account_id"]
        for row in financial
        if row.entity == "journal_line" and row.source_id == account
    )
    for record in records:
        payload = record["payload"]
        if payload["kind"] == "POSITION" and payload.get("control_account_id"):
            payload["control_account_id"] = account_id
        if payload["kind"] == "GL_CONTROL":
            payload.update(account_id=account_id, balance="100")
    ids["account"] = account_id
    return financial + [
        source("inventory_report_record", uuid.uuid4(), record) for record in records
    ], ids


def parameters(code, ids):
    values = {"as_of": "2026-04-30"}
    if code in {"ITEM_LEDGER", "STOCK_MOVEMENT"}:
        values["date_from"] = "2026-04-01"
    if code == "ITEM_LEDGER":
        values["item_id"] = ids["item"]
    return values
