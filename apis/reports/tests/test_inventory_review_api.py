"""Exercise the review fixes through source ingestion, jobs, paging and exports."""

import csv
import io

import pytest
from conftest import COMPANY, headers
from fixtures import source
from inventory_fixture import inventory_dataset
from test_foundation import generation, load
from test_inventory_api import create, finish
from test_inventory_review_fixes import attach_cost_details
from test_native_ledger import prepared


async def cost_generation(app, client, *, native):
    facts, ids = inventory_dataset()
    attach_cost_details([f.data for f in facts if f.entity == "inventory_report_record"], ids)
    facts = [source(f.entity, f.source_id, f.data) for f in facts]
    if native:
        identities, _, _ = await prepared(app, dataset=(facts, ids))
        identity = str(identities[2])
    else:
        created = await generation(client, f"/v1/companies/{COMPANY}")
        await load(app, created["id"], facts)
        identity = created["id"]
    app.state.settings.framework_enabled = True
    return identity, ids


@pytest.mark.parametrize("native", [False, True])
async def test_cost_detail_reads_complete_frozen_history_and_enforces_authority(
    app, client, native
):
    identity, _ = await cost_generation(app, client, native=native)
    response = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "STOCK_VALUATION",
            "generation_id": identity,
            "parameters": {"as_of": "2026-04-30", "include_cost_details": True},
        },
    )
    assert response.status_code == 202, response.text
    target, _ = await finish(app, client, response.json()["id"])
    page = await client.get(target + "/rows", headers=headers())
    rows = [r["data"] for r in page.json()["items"]]
    assert {"COST_LAYER", "COST_POOL"} <= {r["row_kind"] for r in rows}
    denied = [
        {
            "entity_type": "accounting.account",
            "field_key": "name",
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
    ]
    assert (await client.get(target + "/rows", headers=headers(policies=denied))).status_code == 403


@pytest.mark.parametrize("format_name", ["CSV", "XLSX", "HTML", "PDF"])
async def test_cost_detail_exports_preserve_separate_balance_and_detail_measures(
    app, client, tmp_path, format_name
):
    identity, _ = await cost_generation(app, client, native=True)
    response = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "STOCK_VALUATION",
            "generation_id": identity,
            "parameters": {"as_of": "2026-04-30", "include_cost_details": True},
            "view": "audit",
        },
    )
    assert response.status_code == 202, response.text
    target, result = await finish(app, client, response.json()["id"])
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    exported_response = await client.post(
        target + "/exports", headers=headers(), json={"format": format_name, "view": "audit"}
    )
    assert exported_response.status_code == 202, exported_response.text
    exported = exported_response.json()
    download = f"/v2/companies/{COMPANY}/report-exports/{exported['id']}"
    _, output = await finish(app, client, exported["id"], kind="report-exports")
    assert output["result"]["row_count"] == result["completed_rows"]
    token = (await client.get(download + "/download-token", headers=headers())).json()["token"]
    response = await client.get(download + "/download", headers=headers(), params={"token": token})
    assert response.status_code == 200, response.text
    if format_name == "CSV":
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        detail = [r for r in rows if r["Row Kind"] in {"COST_LAYER", "COST_POOL"}]
        assert len(detail) == 3
        assert all(not r["Carrying Value"] and not r["Quantity"] for r in detail)
        assert all(r["Remaining Value"] for r in detail)
        assert all(r["Position Id"] for r in detail)
        assert all(r["Layer Id"] or r["Pool Id"] for r in detail)


async def test_batch_lot_filter_survives_api_drilldown(app, client):
    _, result, ids = await create(app, client, "BATCH_SUMMARY", native=True)
    response = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "BATCH_SUMMARY",
            "generation_id": result["generation_id"],
            "parameters": {
                "as_of": "2026-04-30",
                "lot_id": ids["old_lot"],
                "include_history": True,
            },
        },
    )
    assert response.status_code == 202, response.text
    target, _ = await finish(app, client, response.json()["id"])
    rows = (await client.get(target + "/rows", headers=headers())).json()["items"]
    assert rows and all(r["data"]["lot_id"] == ids["old_lot"] for r in rows)
    link = next(
        item for row in rows for item in row["drilldowns"] if item["key"] == "stock_item_entries"
    )
    response = await client.post(
        target + "/drilldowns", headers=headers(), json={"token": link["token"]}
    )
    assert response.status_code == 202, response.text
    _, child = await finish(app, client, response.json()["id"])
    assert child["parameters"]["lot_id"] == ids["old_lot"]


async def test_cost_detail_admission_does_not_use_balance_only_budget(app, client):
    identity, _ = await cost_generation(app, client, native=True)
    app.state.settings.native_result_limit = 12
    response = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "STOCK_VALUATION",
            "generation_id": identity,
            "parameters": {"as_of": "2026-04-30", "include_cost_details": True},
        },
    )
    assert response.status_code == 409, response.text
