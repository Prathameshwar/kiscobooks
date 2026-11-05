"""Independent exact examples for business-report arithmetic and native source checks."""

import uuid

from inventory_fixture import inventory_records

from reports.domain.analytics_common import stock_index

VALUES = {"date_from": "2026-04-01", "date_to": "2026-04-30", "grain": "MONTH"}


def document(amount="1000", *, day="2026-04-10", kind="SALES", currency="INR", party=None):
    party = party or str(uuid.uuid4())
    line = str(uuid.uuid4())
    return {
        "invoice_id": str(uuid.uuid4()),
        "invoice_kind": kind,
        "voucher_id": str(uuid.uuid4()),
        "party_id": party,
        "party_account_id": str(uuid.uuid4()),
        "account_name": "Buyer",
        "customer_name": "Buyer",
        "currency": currency,
        "posting_date": day,
        "bill_reference": "INV-" + str(uuid.uuid4())[:8],
        "commercial_total": amount,
        "supplies": [
            {
                "id": str(uuid.uuid4()),
                "item_line_key": line,
                "commercial": amount,
                "description": "Widget",
                "supply_kind": "GOODS",
            }
        ],
        "components": [],
    }


def stock_for(document):
    records, ids = inventory_records()
    movement = next(
        row["payload"]
        for row in records
        if row["payload"]["kind"] == "MOVEMENT" and row["payload"]["action"] == "SALE"
    )
    movement.update(
        voucher_id=document["voucher_id"], line_id=document["supplies"][0]["item_line_key"]
    )
    return stock_index(records), ids
