"""Completion regressions over real retained owner cuts and native jobs."""

import datetime as dt
import io
import json
import os
import unicodedata
from pathlib import Path
from zipfile import ZipFile

import pytest
from conftest import headers
from pypdf import PdfReader
from test_analytics_api import BASE, complete, source
from test_opening_migration_modes import prepared, ytd_dataset

from reports.domain.reporting.drilldowns import parameters_for
from reports.tasks.analytics_catalog import CODES
from reports.tasks.report_catalog import catalog


@pytest.mark.parametrize("period", ["CURRENT", "COMPARATIVE"])
def test_imported_analytics_drilldowns_preserve_only_available_detail(period):
    parameters = {
        "date_from": "2026-04-01",
        "date_to": "2026-04-30",
        "comparative_from": "2026-04-01",
        "comparative_to": "2026-04-15",
    }
    row = {"account_id": "01990000-0000-7000-8000-000000000001", "period": period}
    selected = parameters_for("account_entries", parameters, row, "2026-04-02", retained_only=True)
    assert selected["date_from"] == "2026-04-02"
    assert selected["date_to"] == ("2026-04-15" if period == "COMPARATIVE" else "2026-04-30")
    assert parameters["date_from"] == "2026-04-01"
    assert (
        parameters_for("account_entries", parameters, row, "2026-05-01", retained_only=True) is None
    )
    assert parameters_for("row_detail", parameters, row, None, retained_only=True) == {}


@pytest.mark.parametrize(
    "code", sorted(CODES | {"BALANCE_CONTINUITY", "SOURCE_RECONCILIATION", "INVOICE_GL_BRIDGE"})
)
async def test_every_analytics_page_view_executes_and_exports(app, client, tmp_path, code):
    generation = await source(app)
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    parameters = (
        {}
        if code == "SOURCE_RECONCILIATION"
        else {
            "date_from": "2027-04-01" if code == "BALANCE_CONTINUITY" else "2026-04-01",
            "date_to": "2028-03-31" if code == "BALANCE_CONTINUITY" else "2026-04-30",
        }
    )
    definition = (await client.get(BASE + "/report-definitions/" + code, headers=headers())).json()
    for view in catalog().resolve(code).definition.views:
        response = await client.post(
            BASE + "/report-runs",
            headers=headers(),
            json={
                "code": code,
                "generation_id": generation,
                "parameters": parameters,
                "view": view.key,
            },
        )
        assert response.status_code == 202, response.text
        identity = response.json()["id"]
        await complete(app, identity)
        endpoint = BASE + "/report-runs/" + identity
        job = (await client.get(endpoint, headers=headers())).json()
        assert job["status"] == "COMPLETE", job
        result = await client.get(endpoint + "/rows?limit=200", headers=headers())
        assert result.status_code == 200, result.text
        assert result.json()["page"]["next_cursor"] is None
        if code in {"BALANCE_CONTINUITY", "SOURCE_RECONCILIATION", "INVOICE_GL_BRIDGE"}:
            assert result.json()["items"], code
        links = [
            link
            for row in result.json()["items"]
            for link in row.get("drilldowns", [])
            if link["method"] == "POST"
        ]
        if links:
            child = await client.post(
                endpoint + "/drilldowns", headers=headers(), json={"token": links[0]["token"]}
            )
            assert child.status_code == 202, child.text
            await complete(app, child.json()["id"])
            detail = (
                await client.get(BASE + "/report-runs/" + child.json()["id"], headers=headers())
            ).json()
            assert detail["status"] == "COMPLETE", detail
        evidence = os.environ.get("ANALYTICS_COMPLETION_EVIDENCE")
        output = Path(evidence) / code / view.key if evidence else None
        if output:
            output.mkdir(parents=True, exist_ok=True)
            (output / "workspace.json").write_text(
                json.dumps({"definition": definition, "job": job, "rows": result.json()}),
                encoding="utf-8",
            )
        for kind in ("CSV", "XLSX", "PDF"):
            created = await client.post(
                endpoint + "/exports", headers=headers(), json={"format": kind, "view": view.key}
            )
            assert created.status_code == 202, created.text
            await complete(app, created.json()["id"])
            exported = BASE + "/report-exports/" + created.json()["id"]
            status = (await client.get(exported, headers=headers())).json()
            assert status["status"] == "COMPLETE", status
            token = await client.get(exported + "/download-token", headers=headers())
            download = await client.get(
                exported + "/download", headers=headers(), params={"token": token.json()["token"]}
            )
            assert download.status_code == 200, download.text[:100]
            if kind == "PDF":
                pages = PdfReader(io.BytesIO(download.content)).pages
                assert pages
                if code in {"BUYER_PROFIT", "PRODUCT_PROFIT"}:
                    first = unicodedata.normalize("NFKC", pages[0].extract_text())
                    table = first[first.index("Period"):]
                    for column in view.columns:
                        if column.kind == "MONEY":
                            assert column.title in table, (code, view.key, column.title)
                if (
                    code
                    in {
                        "BALANCE_CONTINUITY",
                        "SOURCE_RECONCILIATION",
                        "INVOICE_GL_BRIDGE",
                        "BUYER_PROFIT",
                        "PRODUCT_PROFIT",
                    }
                    and view.key == "default"
                ):
                    text = " ".join(unicodedata.normalize("NFKC", pages[0].extract_text()).split())
                    for column in view.columns:
                        if column.kind == "MONEY":
                            assert column.title in text
            elif kind == "XLSX":
                assert "xl/workbook.xml" in ZipFile(io.BytesIO(download.content)).namelist()
            else:
                assert view.columns[0].title in download.content.decode("utf-8-sig")
            if output:
                (output / ("report." + kind.lower())).write_bytes(download.content)


@pytest.mark.parametrize(
    ("code", "title"),
    [
        ("BALANCE_CONTINUITY", "Year continuity"),
        ("SOURCE_RECONCILIATION", "Snapshot controls"),
        ("INVOICE_GL_BRIDGE", "Posted invoice effects"),
    ],
)
def test_controls_offer_reviewed_business_columns_and_source_details(code, title):
    views = catalog().resolve(code).definition.views
    assert views[0].title == title
    assert not any(column.key.endswith("_id") for column in views[0].columns)
    assert any(column.kind == "MONEY" for column in views[0].columns)
    assert len(views[0].columns) <= 8  # Keep core control amounts together on one PDF band.
    assert len(views) <= 2


@pytest.mark.parametrize("code", ["PROFIT_MARGIN_ANALYSIS", "EXPENSE_PROFIT_LEAKAGE"])
async def test_profit_analytics_preserves_imported_ytd_without_inventing_invoice_history(
    app, client, code
):
    facts, _ = ytd_dataset()
    generation = await prepared(app, facts, dt.date(2026, 4, 2))
    app.state.settings.framework_enabled = app.state.settings.native_queries_enabled = True
    response = await client.post(
        BASE + "/report-runs",
        headers=headers(),
        json={
            "code": code,
            "generation_id": str(generation),
            "parameters": {"date_from": "2026-04-01", "date_to": "2026-04-30"},
            "view": "accounts" if code == "PROFIT_MARGIN_ANALYSIS" else "default",
        },
    )
    assert response.status_code == 202, response.text
    await complete(app, response.json()["id"])
    result = await client.get(BASE + "/report-runs/" + response.json()["id"], headers=headers())
    assert result.json()["status"] == "COMPLETE", result.text
    summary = result.json()["result"]["evidence"]["analytics"]
    assert summary["amounts"]["CURRENT"]["INR"]["net_profit"] == "260.0000"
    assert any("imported YTD" in notice for notice in summary["notices"])
    assert all(row["date"] >= "2026-04-02" for row in summary["trends"])
    endpoint = BASE + "/report-runs/" + response.json()["id"]
    rows = (await client.get(endpoint + "/rows", headers=headers())).json()["items"]
    link = next(
        link for row in rows for link in row["drilldowns"] if link["key"] == "account_entries"
    )
    child = await client.post(
        endpoint + "/drilldowns", headers=headers(), json={"token": link["token"]}
    )
    assert child.status_code == 202, child.text
    assert child.json()["parameters"]["date_from"] == "2026-04-02"
    await complete(app, child.json()["id"])
    detail = await client.get(BASE + "/report-runs/" + child.json()["id"], headers=headers())
    assert detail.json()["status"] == "COMPLETE", detail.text
