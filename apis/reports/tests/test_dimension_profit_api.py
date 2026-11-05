"""Native invoice/stock/GL evidence for the two dimension-profit reports."""

import uuid

import pytest
from conftest import headers
from fixtures import source
from inventory_fixture import inventory_records
from invoice_fixture import invoice_dataset
from test_analytics_api import BASE, PARAMS, complete
from test_native_ledger import prepared


def profit_dataset():
    facts, financial_ids = invoice_dataset()
    records, ids = inventory_records()
    templates = {row.entity: row.data for row in facts}
    stock_account = uuid.UUID(ids["account"])
    cash = next(row.data for row in facts if row.entity == "account" and row.data["kind"] == "CASH")
    facts.append(
        source(
            "account", stock_account, cash | {"code": "STOCK", "name": "Stock", "kind": "GENERAL"}
        )
    )
    for name, amount, debit, credit, day in (
        ("stock-opening", "1120", str(stock_account), financial_ids["equity"], "2026-04-01"),
        ("stock-cost", "400", financial_ids["expense"], str(stock_account), "2026-04-02"),
    ):
        identity = uuid.uuid4()
        template = next(
            row.data for row in facts if row.entity == "journal" and row.data["number"] == "invoice"
        )
        facts.append(
            source(
                "journal",
                identity,
                template
                | {
                    "kind": "OPENING" if name == "stock-opening" else "MANUAL",
                    "number": name,
                    "source_id": str(identity),
                    "posting_date": day,
                    "document_date": day,
                    "total_debit": amount,
                    "total_credit": amount,
                },
            )
        )
        for sequence, (side, account) in enumerate((("DEBIT", debit), ("CREDIT", credit)), 1):
            facts.append(
                source(
                    "journal_line",
                    uuid.uuid4(),
                    templates["journal_line"]
                    | {
                        "journal_id": str(identity),
                        "account_id": account,
                        "sequence": sequence,
                        "side": side,
                        "amount": amount,
                        "base_amount": amount,
                        "party_id": None,
                        "role": None,
                    },
                )
            )
    line_key = str(uuid.uuid4())
    facts = [
        source(row.entity, row.source_id, row.data | {"item_line_key": line_key})
        if row.entity == "invoice_supply_fact"
        else row
        for row in facts
    ]
    intent = next(row.data for row in facts if row.entity == "voucher_money_intent")
    for record in records:
        payload = record["payload"]
        if payload["kind"] == "MOVEMENT" and payload["action"] == "SALE":
            payload.update(
                voucher_id=intent["voucher_id"], line_id=line_key, effective_date="2026-04-02"
            )
    facts.extend(source("inventory_report_record", uuid.uuid4(), record) for record in records)
    return facts, ids


@pytest.mark.parametrize(
    ("code", "view"),
    [
        ("BUYER_PROFIT", "default"),
        ("BUYER_PROFIT", "invoices"),
        ("PRODUCT_PROFIT", "default"),
        ("PRODUCT_PROFIT", "groups"),
    ],
)
async def test_native_profit_matches_actual_cost_and_group_drilldown(app, client, code, view):
    identities, facts, ids = await prepared(app, dataset=profit_dataset())
    app.state.settings.framework_enabled = app.state.settings.native_queries_enabled = True
    response = await client.post(
        BASE + "/report-runs",
        headers=headers(),
        json={
            "code": code,
            "view": view,
            "generation_id": str(identities[2]),
            "parameters": PARAMS,
        },
    )
    assert response.status_code == 202, response.text
    await complete(app, response.json()["id"])
    endpoint = BASE + "/report-runs/" + response.json()["id"]
    job = (await client.get(endpoint, headers=headers())).json()
    assert job["status"] == "COMPLETE", job
    amounts = job["result"]["evidence"]["analytics"]["amounts"]["CURRENT"]["INR"]
    assert amounts["net_sales"] == "200.0000"
    assert amounts["cost"] == "400.0000" and amounts["gross_profit"] == "-200.0000"
    assert amounts["margin_percent"] == "-100.0000"
    rows = (await client.get(endpoint + "/rows", headers=headers())).json()["items"]
    assert len(rows) == (2 if view == "groups" else 1)
    assert all(not key.startswith("_sales_") for row in rows for key in row["data"])
    if code == "BUYER_PROFIT":
        link = next(link for link in rows[0]["drilldowns"] if link["key"] == "analytics_sales")
        child = await client.post(
            endpoint + "/drilldowns", headers=headers(), json={"token": link["token"]}
        )
        assert child.status_code == 202, child.text
        expected_invoice = rows[0]["data"].get("invoice_id") or next(
            row.source_id for row in facts if row.entity == "invoice_record"
        )
        assert child.json()["parameters"]["invoice_id"] == str(expected_invoice)
        await complete(app, child.json()["id"])
        child_path = BASE + "/report-runs/" + child.json()["id"]
        assert (await client.get(child_path, headers=headers())).json()["status"] == "COMPLETE"
        child_rows = (await client.get(child_path + "/rows", headers=headers())).json()["items"]
        assert len(child_rows) == 1 and child_rows[0]["data"]["invoice_id"] == str(expected_invoice)
    if view == "groups":
        row = next(row for row in rows if row["data"]["group_id"] == ids["child"])
        link = next(link for link in row["drilldowns"] if link["key"] == "profit_group_products")
        child = await client.post(
            endpoint + "/drilldowns", headers=headers(), json={"token": link["token"]}
        )
        assert child.status_code == 202, child.text
        assert child.json()["parameters"]["group_id"] == ids["child"]
        await complete(app, child.json()["id"])
        detail = (
            await client.get(BASE + "/report-runs/" + child.json()["id"], headers=headers())
        ).json()
        assert detail["status"] == "COMPLETE", detail
        assert detail["result"]["evidence"]["analytics"]["amounts"]["CURRENT"]["INR"] == amounts
    if code == "PRODUCT_PROFIT":
        reference = await client.get(
            BASE + "/report-generations/" + str(identities[2]) + "/inventory",
            headers=headers(),
            params={"kind": "GROUP", "object_id": ids["child"]},
        )
        assert reference.status_code == 200, reference.text
        assert reference.json()["items"][0]["name"] == "Child"
