"""Actual immutable native jobs, current authority and binary exports for analytics."""

import io
import json
import os
import unicodedata
import uuid
from pathlib import Path

import pytest
from billing_platform.db import tenant_scope
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from financial_fixture import financial_manifest
from invoice_fixture import invoice_dataset
from sqlalchemy import select
from test_framework_execution import proof
from test_source_versions import staged

from reports.models.source_versions import ReportSourceCut
from reports.tasks.analytics_catalog import CODES
from reports.tasks.framework_worker import process
from reports.tasks.source_publication import publish

BASE = f"/v2/companies/{COMPANY}"
PARAMS = {"date_from": "2026-04-01", "date_to": "2026-04-30"}


async def source(app):
    facts, _ = invoice_dataset()
    identities, _ = await staged(app, source=facts, control=financial_manifest(facts).control)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identities[2])
            )
        await publish(app.state.session_factory, COMPANY, cut.id)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    return str(identities[2])


async def complete(app, identity):
    async def authority(job):
        return proof(job)

    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(identity),
        authority,
    )


@pytest.mark.parametrize("code", sorted(CODES))
async def test_native_business_report_freezes_replays_and_exports_actual_files(
    app, client, tmp_path, code
):
    generation = await source(app)
    body = {"code": code, "generation_id": generation, "parameters": PARAMS}
    key = headers()
    created = await client.post(BASE + "/report-runs", headers=key, json=body)
    assert created.status_code == 202, created.text
    replay = await client.post(BASE + "/report-runs", headers=key, json=body)
    assert replay.json()["id"] == created.json()["id"]
    await complete(app, created.json()["id"])
    target = BASE + "/report-runs/" + created.json()["id"]
    fetched = await client.get(target, headers=headers())
    job = fetched.json()
    assert job["status"] == "COMPLETE", fetched.text
    assert job["result"]["evidence"]["analytics"]["code"] == code
    analytics = job["result"]["evidence"]["analytics"]
    assert analytics["calculation_version"] == 3
    amounts = analytics["amounts"]["CURRENT"]["INR"]
    # Independently recorded fixture: invoice 200, receipt 120, expense 40,
    # opening cash 100. Only 50 of the receipt is allocated, so gross debt is
    # 150 and unapplied credit is 70 (net party GL 80). Document date is March
    # 31; posting date is April 2.
    expected = {
        "BUYER_PROFIT": {"net_sales": "200.0000", "cost": None, "gross_profit": None},
        "PRODUCT_PROFIT": {"net_sales": "200.0000", "cost": None, "gross_profit": None},
        "SALES_PERFORMANCE": {"net_sales": "200.0000", "invoice_count": 1},
        "CUSTOMER_INSIGHTS": {"net_sales": "200.0000", "active_customers": 1},
        "PROFIT_MARGIN_ANALYSIS": {"net_profit": "160.0000", "operating_expenses": "40.0000"},
        "EXPENSE_PROFIT_LEAKAGE": {"net_profit": "160.0000", "total_expenses": "40.0000"},
        "CASH_WORKING_CAPITAL": {
            "opening_cash": "100.0000",
            "cash_receipts": "120.0000",
            "cash_payments": "40.0000",
            "closing_cash": "180.0000",
            "receivables": "150.0000",
            "cash_adjustments": "0.0000",
            "stock_tied_up": None,
        },
    }
    for metric, expected_value in expected[code].items():
        assert amounts[metric] == expected_value, (code, metric, amounts)
    rows = await client.get(target + "/rows?limit=50", headers=headers())
    assert rows.status_code == 200, rows.text
    assert rows.json()["items"]
    assert (await client.get(target, headers=headers(user=uuid.uuid4()))).status_code == 403
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    definition = await client.get(BASE + "/report-definitions/" + code, headers=headers())
    assert definition.status_code == 200
    assert {"CSV", "XLSX", "PDF"} <= set(definition.json()["formats"])
    if os.environ.get("ANALYTICS_EVIDENCE_DIR"):
        output = Path(os.environ["ANALYTICS_EVIDENCE_DIR"]) / code
        output.mkdir(parents=True, exist_ok=True)
        (output / "definition.json").write_text(json.dumps(definition.json()), encoding="utf-8")
    for kind in ("CSV", "XLSX", "PDF"):
        exported = await client.post(target + "/exports", headers=headers(), json={"format": kind})
        assert exported.status_code == 202, exported.text
        await complete(app, exported.json()["id"])
        export_path = BASE + "/report-exports/" + exported.json()["id"]
        status = await client.get(export_path, headers=headers())
        assert status.json()["status"] == "COMPLETE", status.text
        assert (
            await client.get(export_path + "/download-token", headers=headers(user=uuid.uuid4()))
        ).status_code == 403
        token = await client.get(export_path + "/download-token", headers=headers())
        download = await client.get(
            export_path + "/download", headers=headers(), params={"token": token.json()["token"]}
        )
        assert download.status_code == 200
        if kind == "PDF":
            from pypdf import PdfReader

            assert download.content.startswith(b"%PDF")
            text = " ".join(
                page.extract_text() for page in PdfReader(io.BytesIO(download.content)).pages
            )
            assert job["title"] in unicodedata.normalize("NFKC", text)
        elif kind == "XLSX":
            from zipfile import ZipFile

            with ZipFile(io.BytesIO(download.content)) as book:
                assert b"<sheetData>" in book.read("xl/worksheets/sheet1.xml")
        else:
            assert "period" in download.text.casefold() and "INR" in download.text
        if os.environ.get("ANALYTICS_EVIDENCE_DIR"):
            output = Path(os.environ["ANALYTICS_EVIDENCE_DIR"]) / code
            output.mkdir(parents=True, exist_ok=True)
            (output / ("report." + kind.lower())).write_bytes(download.content)
            (output / "preparation.json").write_text(json.dumps(job), encoding="utf-8")
            (output / "rows.json").write_text(json.dumps(rows.json()), encoding="utf-8")


@pytest.mark.parametrize("code", sorted(CODES))
async def test_business_report_deny_and_invalid_period(app, client, code):
    app.state.settings.framework_enabled = True
    target = BASE + "/report-definitions/" + code
    assert (await client.get(target)).status_code == 401
    assert (
        await client.get(
            target, headers=headers(permissions=PERMISSIONS - {"accounting.finance.read"})
        )
    ).status_code == 403
    assert (await client.get(target, headers=headers(company=uuid.uuid4()))).status_code == 401
    policy = [{"access": "read", "effect": "deny", "field": "amount"}]
    assert (await client.get(target, headers=headers(policies=policy))).status_code == 403
    generation = await source(app)
    bad = await client.post(
        BASE + "/report-runs",
        headers=headers(),
        json={
            "code": code,
            "generation_id": generation,
            "parameters": PARAMS | {"date_to": "2026-03-31"},
        },
    )
    assert bad.status_code == 422, bad.text
    outside = await client.post(
        BASE + "/report-runs",
        headers=headers(),
        json={
            "code": code,
            "generation_id": generation,
            "parameters": PARAMS | {"date_from": "2025-01-01"},
        },
    )
    assert outside.status_code == 409


@pytest.mark.parametrize("code", sorted(CODES))
async def test_every_analytics_view_uses_a_native_frozen_result(app, client, tmp_path, code):
    generation = await source(app)
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    definition = await client.get(BASE + "/report-definitions/" + code, headers=headers())
    assert definition.status_code == 200
    evidence_directory = os.environ.get("ANALYTICS_EVIDENCE_DIR")
    if evidence_directory:
        output = Path(evidence_directory) / code
        output.mkdir(parents=True, exist_ok=True)
        (output / "definition.json").write_text(json.dumps(definition.json()), encoding="utf-8")
    for view in definition.json()["definition"]["views"]:
        created = await client.post(
            BASE + "/report-runs",
            headers=headers(),
            json={
                "code": code,
                "generation_id": generation,
                "parameters": PARAMS,
                "view": view["key"],
            },
        )
        assert created.status_code == 202, created.text
        await complete(app, created.json()["id"])
        target = BASE + "/report-runs/" + created.json()["id"]
        fetched = await client.get(target, headers=headers())
        assert fetched.json()["status"] == "COMPLETE", fetched.text
        listed = await client.get(target + "/rows?limit=50", headers=headers())
        assert listed.status_code == 200
        assert fetched.json()["result"]["evidence"]["analytics"]["view"] == view["key"]


async def test_cash_definition_requires_bank_evidence_access(app, client):
    app.state.settings.framework_enabled = True
    denied = await client.get(
        BASE + "/report-definitions/CASH_WORKING_CAPITAL",
        headers=headers(permissions=PERMISSIONS - {"accounting.bank.read"}),
    )
    assert denied.status_code == 403
