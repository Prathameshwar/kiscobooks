import csv
import io
import uuid
import zipfile

import pytest
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from inventory_fixture import inventory_dataset, parameters
from test_foundation import generation, load
from test_framework_execution import proof
from test_framework_exports import new_export
from test_native_ledger import prepared

from reports.domain.reporting.inventory import CODES
from reports.tasks.framework_worker import process


async def authority(job):
    return proof(job)


async def finish(app, client, identity, *, kind="report-runs"):
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(identity),
        authority,
    )
    target = f"/v2/companies/{COMPANY}/{kind}/{identity}"
    result = await client.get(target, headers=headers())
    assert result.json()["status"] == "COMPLETE", result.text
    return target, result.json()


async def create(app, client, code, *, native=False):
    facts, ids = inventory_dataset()
    app.state.settings.framework_enabled = True
    if native:
        identities, _, _ = await prepared(app, dataset=(facts, ids))
        source_id = str(identities[2])
    else:
        source = await generation(client, f"/v1/companies/{COMPANY}")
        await load(app, source["id"], facts)
        source_id = source["id"]
    base = f"/v2/companies/{COMPANY}/report-runs"
    body = {"code": code, "generation_id": source_id, "parameters": parameters(code, ids)}
    token = headers()
    response = await client.post(base, headers=token, json=body)
    assert response.status_code == 202, response.text
    repeat = await client.post(base, headers=token, json=body)
    assert repeat.json()["id"] == response.json()["id"]
    target, result = await finish(app, client, response.json()["id"])
    return target, result, ids


@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize("native", [False, True])
async def test_all_ten_run_publish_page_drill_and_enforce_scope(app, client, code, native):
    target, result, ids = await create(app, client, code, native=native)
    assert result["result"]["evidence"]["inventory_coverage"]["policy_hash"] == "a" * 64
    collected, cursor = [], None
    while True:
        page = await client.get(
            target + "/rows",
            headers=headers(),
            params={
                "limit": 2,
                **({"cursor": cursor} if cursor else {}),
            },
        )
        assert page.status_code == 200, page.text
        collected.extend(page.json()["items"])
        cursor = page.json()["page"]["next_cursor"]
        if cursor is None:
            break
    assert collected and len(collected) == result["completed_rows"]
    assert (await client.get(target + "/rows")).status_code == 401
    assert (
        await client.get(
            target + "/rows",
            headers=headers(
                permissions=PERMISSIONS - {"item.read"},
            ),
        )
    ).status_code == 403
    assert (
        await client.get(target + "/rows", headers=headers(user=uuid.uuid4()))
    ).status_code == 403
    other = uuid.uuid4()
    assert (
        await client.get(target.replace(str(COMPANY), str(other)), headers=headers(company=other))
    ).status_code == 403
    assert (
        await client.get(target + "/rows", headers=headers(tenant=uuid.uuid4()))
    ).status_code == 404
    denied = [
        {
            "entity_type": "catalog.item",
            "field_key": "name",
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
    ]
    assert (await client.get(target + "/rows", headers=headers(policies=denied))).status_code == 403
    links = [
        link
        for row in collected
        for link in row["drilldowns"]
        if link["key"] in {"stock_item_entries", "stock_group_items"}
    ]
    if links:
        child = await client.post(
            target + "/drilldowns", headers=headers(), json={"token": links[0]["token"]}
        )
        assert child.status_code == 202, child.text
        _, child_result = await finish(app, client, child.json()["id"])
        assert child_result["generation_id"] == result["generation_id"]


@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize("format_name", ["CSV", "XLSX", "HTML", "PDF"])
async def test_all_ten_export_through_existing_framework(app, client, tmp_path, code, format_name):
    target, result, _ = await create(app, client, code)
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    exported, download = await new_export(client, target, format_name)
    _, output = await finish(app, client, exported["id"], kind="report-exports")
    token = await client.get(download + "/download-token", headers=headers())
    assert token.status_code == 200, token.text
    response = await client.get(
        download + "/download", headers=headers(), params={"token": token.json()["token"]}
    )
    assert response.status_code == 200, response.text
    assert output["result"]["row_count"] == result["completed_rows"]
    if format_name == "CSV":
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        assert len(rows) == result["completed_rows"]
        assert "Item Code" in rows[0] or "Group Code" in rows[0]
    elif format_name == "XLSX":
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.testzip() is None
    elif format_name == "PDF":
        from pypdf import PdfReader

        assert PdfReader(io.BytesIO(response.content)).pages
    else:
        assert "<html" in response.text
        assert "All retained periods" not in response.text
    revoked = await client.get(
        download + "/download",
        headers=headers(
            permissions=PERMISSIONS - {"warehouse.read"},
        ),
        params={"token": token.json()["token"]},
    )
    assert revoked.status_code == 403


async def test_missing_inventory_coverage_is_rejected_at_admission(app, client):
    source = await generation(client, f"/v1/companies/{COMPANY}")
    await load(app, source["id"])
    app.state.settings.framework_enabled = True
    response = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "STOCK_SUMMARY",
            "generation_id": source["id"],
            "parameters": {"as_of": "2026-04-30"},
        },
    )
    assert response.status_code == 409
    assert "inventory source coverage" in response.text


async def test_final_review_filtered_group_drilldown_keeps_scope_and_omits_broader_group(
    app, client
):
    _, result, ids = await create(app, client, "STOCK_GROUP_SUMMARY")
    filters = {
        "as_of": "2026-04-30",
        "group_id": ids["child"],
        "location_id": ids["location"],
        "include_inactive": False,
    }
    response = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "STOCK_GROUP_SUMMARY",
            "generation_id": result["generation_id"],
            "parameters": filters,
        },
    )
    assert response.status_code == 202, response.text
    target, _ = await finish(app, client, response.json()["id"])
    page = await client.get(target + "/rows", headers=headers())
    rows = page.json()["items"]
    ancestors = [r for r in rows if r["data"]["group_id"] == ids["group"]]
    assert ancestors
    assert not any(
        link["key"] == "stock_group_items" for r in ancestors for link in r["drilldowns"]
    )
    leaf = next(r for r in rows if r["data"]["group_id"] == ids["child"])
    link = next(link for link in leaf["drilldowns"] if link["key"] == "stock_group_items")
    child = await client.post(
        target + "/drilldowns", headers=headers(), json={"token": link["token"]}
    )
    assert child.status_code == 202, child.text
    _, completed = await finish(app, client, child.json()["id"])
    assert completed["generation_id"] == result["generation_id"]
    assert all(completed["parameters"][key] == value for key, value in filters.items())


async def test_final_review_short_movement_period_exports_reconciled_balances(
    app, client, tmp_path
):
    _, result, _ = await create(app, client, "STOCK_MOVEMENT")
    response = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "STOCK_MOVEMENT",
            "generation_id": result["generation_id"],
            "parameters": {"as_of": "2026-04-30", "date_from": "2026-04-20"},
        },
    )
    assert response.status_code == 202, response.text
    target, _ = await finish(app, client, response.json()["id"])
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    exported, download = await new_export(client, target, "CSV")
    await finish(app, client, exported["id"], kind="report-exports")
    token = await client.get(download + "/download-token", headers=headers())
    assert token.status_code == 200, token.text
    response = await client.get(
        download + "/download", headers=headers(), params={"token": token.json()["token"]}
    )
    assert response.status_code == 200, response.text
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    row = next(r for r in rows if r["Item Code"] == "ITEM" and r["Owner"] == "OWN")
    assert (row["Opening"], row["Inward"], row["Outward"], row["Quantity"]) == (
        "70.0000",
        "0.0000",
        "0.0000",
        "70.0000",
    )
    assert (
        row["Opening Value"],
        row["Inward Value"],
        row["Outward Value"],
        row["Closing Value"],
    ) == (
        "700.0000",
        "0.0000",
        "0.0000",
        "700.0000",
    )


async def test_review_balance_report_budget_excludes_unread_movement_history(app, client):
    facts, ids = inventory_dataset()
    identities, _, _ = await prepared(app, dataset=(facts, ids))
    app.state.settings.framework_enabled = True
    app.state.settings.native_result_limit = 12
    response = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "STOCK_SUMMARY",
            "generation_id": str(identities[2]),
            "parameters": {"as_of": "2026-04-30"},
        },
    )
    assert response.status_code == 202, response.text
    await finish(app, client, response.json()["id"])


@pytest.mark.parametrize("native", [False, True])
async def test_stock_gl_matches_independent_financial_source(app, client, native):
    from billing_platform.db import tenant_scope

    from reports.models.core import ReportGeneration
    from reports.tasks.common import get
    from reports.tasks.inventory_source import records, verify_gl

    facts, ids = inventory_dataset()
    if native:
        identities, _, _ = await prepared(app, dataset=(facts, ids))
        identity = identities[2]
    else:
        created = await generation(client, f"/v1/companies/{COMPANY}")
        await load(app, created["id"], facts)
        identity = uuid.UUID(created["id"])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await get(db, COMPANY, ReportGeneration, identity)
            values, _ = await records(db, row, "STOCK_VALUATION", 100000)
            await verify_gl(db, row, values, 100000)


async def test_batch_history_is_a_frozen_api_run_with_source_movements(app, client):
    facts, ids = inventory_dataset()
    identities, _, _ = await prepared(app, dataset=(facts, ids))
    app.state.settings.framework_enabled = True
    response = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "BATCH_SUMMARY",
            "generation_id": str(identities[2]),
            "parameters": {"as_of": "2026-04-30", "item_id": ids["item"], "include_history": True},
        },
    )
    assert response.status_code == 202, response.text
    target, _ = await finish(app, client, response.json()["id"])
    rows = (await client.get(target + "/rows", headers=headers())).json()["items"]
    assert any(row["data"]["row_kind"] == "BATCH_MOVEMENT" for row in rows)


async def test_review_stock_gl_control_is_checked_against_frozen_financial_source(app, client):
    facts, ids = inventory_dataset()
    from fixtures import source

    corrupted = []
    for fact in facts:
        if (
            fact.entity == "inventory_report_record"
            and fact.data["payload"]["kind"] == "GL_CONTROL"
        ):
            data = {"payload": fact.data["payload"] | {"balance": "720"}}
            fact = source(fact.entity, fact.source_id, data)
        corrupted.append(fact)
    source_generation = await generation(client, f"/v1/companies/{COMPANY}")
    await load(app, source_generation["id"], corrupted)
    app.state.settings.framework_enabled = True
    response = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "STOCK_VALUATION",
            "generation_id": source_generation["id"],
            "parameters": {"as_of": "2026-04-30"},
        },
    )
    assert response.status_code == 202, response.text
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(response.json()["id"]),
        authority,
    )
    result = await client.get(
        f"/v2/companies/{COMPANY}/report-runs/{response.json()['id']}", headers=headers()
    )
    assert result.json()["status"] == "BLOCKED"
    assert result.json()["failure_code"] == "REPORT_VERIFICATION_FAILED"
