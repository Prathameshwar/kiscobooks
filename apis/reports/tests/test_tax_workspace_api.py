"""Real native tax runs, signed navigation, private files and revocation."""

import csv
import io
import uuid
import zipfile

import pytest
from billing_platform.db import tenant_scope
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from financial_fixture import financial_manifest
from sqlalchemy import select
from test_framework_execution import proof
from test_framework_exports import new_export
from test_invoice_reports import tax_dataset
from test_source_versions import staged
from test_tax_workspace import credit_history_dataset

from reports.models.source_versions import ReportSourceCut
from reports.tasks.framework_worker import process
from reports.tasks.source_publication import publish


async def finish(app, client, identity, kind="report-runs"):
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
    target = f"/v2/companies/{COMPANY}/{kind}/{identity}"
    result = await client.get(target, headers=headers())
    assert result.json()["status"] == "COMPLETE", result.text
    return target, result.json()


async def create(app, client, code="INVOICE_TAX_REGISTER", view="default"):
    facts = credit_history_dataset() if code == "INVOICE_CREDIT_REGISTER" else tax_dataset()[0]
    app.state.tax_other_ledger = str(
        next(
            row.source_id for row in facts if row.entity == "account" and row.data["code"] == "CASH"
        )
    )
    facts.sort(key=lambda row: (row.entity, str(row.source_id)))
    identities, _ = await staged(app, source=facts, control=financial_manifest(facts).control)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identities[2])
            )
        await publish(app.state.session_factory, COMPANY, cut.id)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    created = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": code,
            "generation_id": str(identities[2]),
            "parameters": {"date_from": "2026-05-01", "date_to": "2026-05-31"}
            if view == "events"
            else {"date_from": "2026-04-01", "date_to": "2026-04-30"},
            "view": view,
        },
    )
    assert created.status_code == 202, created.text
    return await finish(app, client, created.json()["id"])


@pytest.mark.parametrize(
    "code", ["INVOICE_TAX_REGISTER", "INVOICE_CREDIT_REGISTER", "TAX_GL_BRIDGE"]
)
async def test_tax_register_native_totals_scope_and_signed_journal_navigation(app, client, code):
    target, run = await create(app, client, code)
    amount_key = {
        "INVOICE_TAX_REGISTER": "tax_amount",
        "INVOICE_CREDIT_REGISTER": "pending",
        "TAX_GL_BRIDGE": "credit",
    }[code]
    assert run["result"]["evidence"]["tax_summary"]["amounts"]["INR"][amount_key] == "20.0000"
    rows = await client.get(target + "/rows", headers=headers())
    row = rows.json()["items"][0]
    assert row["data"]["bill_reference"] == "INV-1"
    assert (
        await client.get(
            target, headers=headers(permissions=PERMISSIONS - {"accounting.account.read"})
        )
    ).status_code == 403
    assert (await client.get(target, headers=headers(user=uuid.uuid4()))).status_code == 403
    foreign_company = uuid.uuid4()
    assert (
        await client.get(
            target.replace(str(COMPANY), str(foreign_company)),
            headers=headers(company=foreign_company),
        )
    ).status_code == 403
    links = [
        link
        for link in row["drilldowns"]
        if link["method"] == "POST" and link["key"] == "journal_entries"
    ]
    child = await client.post(
        target + "/drilldowns", headers=headers(), json={"token": links[0]["token"]}
    )
    assert child.status_code == 202, child.text
    _, detail = await finish(app, client, child.json()["id"])
    assert detail["generation_id"] == run["generation_id"]
    assert detail["parameters"]["date_from"] == "2026-04-02"


@pytest.mark.parametrize("format_name", ["CSV", "XLSX", "HTML", "PDF"])
@pytest.mark.parametrize(
    "code,view",
    [
        ("INVOICE_TAX_REGISTER", "default"),
        ("INVOICE_CREDIT_REGISTER", "default"),
        ("TAX_GL_BRIDGE", "default"),
        ("INVOICE_CREDIT_REGISTER", "events"),
        ("TAX_GL_BRIDGE", "full"),
    ],
)
async def test_tax_register_native_files_and_download_revocation(
    app, client, tmp_path, format_name, code, view
):
    target, run = await create(app, client, code, view)
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    if view != "default":
        created = await client.post(
            target + "/exports", headers=headers(), json={"format": format_name, "view": view}
        )
        assert created.status_code == 202, created.text
        job = created.json()
        download = f"/v2/companies/{COMPANY}/report-exports/{job['id']}"
    else:
        job, download = await new_export(client, target, format_name)
    _, result = await finish(app, client, job["id"], "report-exports")
    grant = await client.get(download + "/download-token", headers=headers())
    token = {"token": grant.json()["token"]}
    output = await client.get(download + "/download", headers=headers(), params=token)
    assert output.status_code == 200, output.text
    assert result["result"]["row_count"] == run["completed_rows"]
    if format_name == "CSV":
        rows = list(csv.DictReader(io.StringIO(output.content.decode("utf-8-sig"))))
        if view == "events":
            assert rows[0]["Event Amount"] == "20"
            assert rows[0]["Action"] == "VERIFY"
            assert "Pending" not in rows[0]
        elif code == "INVOICE_CREDIT_REGISTER":
            assert rows[0]["Pending"] == "20.0000"
        elif code == "TAX_GL_BRIDGE":
            assert rows[0]["Amount"] == "20"
            # Both views title this column "Tax Ledger" for TAX_GL_BRIDGE now — the
            # "default"/"full" export headers must agree on the same underlying column.
            assert rows[0]["Tax Ledger"] == "Output IGST"
            if view == "full":
                assert rows[0]["Signed Debit"] == "-20.0000"
            else:
                assert "Invoice Id" not in rows[0]
        else:
            assert rows[0]["Tax Amount"] == "20"
    elif format_name == "XLSX":
        with zipfile.ZipFile(io.BytesIO(output.content)) as archive:
            assert archive.testzip() is None
    elif format_name == "PDF":
        from pypdf import PdfReader

        assert PdfReader(io.BytesIO(output.content)).pages
    else:
        assert "Tax report" in output.text
        expected = {
            "INVOICE_CREDIT_REGISTER": "Closing positions as of",
            "INVOICE_TAX_REGISTER": "Each supply counted once",
            "TAX_GL_BRIDGE": "tax-account movement",
        }[code]
        assert (
            "Committed events in the selected period" if view == "events" else expected
        ) in output.text
    denied = await client.get(
        download + "/download",
        headers=headers(permissions=PERMISSIONS - {"accounting.account.read"}),
        params=token,
    )
    assert denied.status_code == 403


async def test_credit_default_and_event_views_enforce_grain(app, client):
    target, result = await create(app, client, "INVOICE_CREDIT_REGISTER")
    summary = result["result"]["evidence"]["tax_summary"]
    assert summary["mode"] == "POSITIONS" and summary["position_count"] == 1
    assert summary["amounts"]["INR"]["pending"] == "20.0000"
    created = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "INVOICE_CREDIT_REGISTER",
            "generation_id": result["generation_id"],
            "parameters": result["parameters"],
            "view": "events",
        },
    )
    assert created.status_code == 202, created.text
    _, events = await finish(app, client, created.json()["id"])
    assert events["result"]["evidence"]["tax_summary"]["mode"] == "EVENTS"
    assert events["completed_rows"] == 0
    selected = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "INVOICE_CREDIT_REGISTER",
            "generation_id": result["generation_id"],
            "parameters": {"date_from": "2026-05-01", "date_to": "2026-05-31"},
            "view": "events",
        },
    )
    assert selected.status_code == 202, selected.text
    _, may = await finish(app, client, selected.json()["id"])
    assert may["completed_rows"] == 1
    assert may["result"]["evidence"]["tax_summary"]["event_amounts"]["INR"]["VERIFY"] == "20.0000"


async def test_tax_bridge_native_full_result_filters_and_typed_validation(app, client):
    target, run = await create(app, client, "TAX_GL_BRIDGE")
    page = await client.get(target + "/rows", headers=headers())
    row = page.json()["items"][0]["data"]
    for selection, expected_count in [
        (
            {
                "tax_ledger_id": row["account_id"],
                "tax_purpose": "OUTPUT_IGST",
                "search": "output igst",
            },
            1,
        ),
        ({"tax_ledger_id": app.state.tax_other_ledger}, 0),
        ({"tax_purpose": "CLAIM"}, 0),
        ({"search": "missing invoice"}, 0),
    ]:
        created = await client.post(
            f"/v2/companies/{COMPANY}/report-runs",
            headers=headers(),
            json={
                "code": "TAX_GL_BRIDGE",
                "generation_id": run["generation_id"],
                "parameters": run["parameters"] | selection,
            },
        )
        assert created.status_code == 202, created.text
        _, result = await finish(app, client, created.json()["id"])
        assert result["completed_rows"] == expected_count
        assert result["result"]["evidence"]["tax_summary"]["ledger_count"] == expected_count
    invalid = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "INVOICE_TAX_REGISTER",
            "generation_id": run["generation_id"],
            "parameters": {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "tax_ledger_id": row["account_id"],
            },
        },
    )
    assert invalid.status_code == 422
    foreign = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "TAX_GL_BRIDGE",
            "generation_id": run["generation_id"],
            "parameters": run["parameters"] | {"tax_ledger_id": str(uuid.uuid4())},
        },
    )
    assert foreign.status_code == 202
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(foreign.json()["id"]),
        _authority,
    )
    blocked = await client.get(
        f"/v2/companies/{COMPANY}/report-runs/" + foreign.json()["id"], headers=headers()
    )
    assert blocked.json()["status"] == "BLOCKED"
    assert blocked.json()["failure_code"] == "REPORT_VERIFICATION_FAILED"


async def _authority(job):
    return proof(job)


@pytest.mark.parametrize("format_name", ["CSV", "HTML"])
async def test_tax_comparative_exports_label_rows_and_preserve_current_totals(
    app, client, tmp_path, format_name
):
    _, run = await create(app, client, "TAX_GL_BRIDGE")
    created = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "TAX_GL_BRIDGE",
            "generation_id": run["generation_id"],
            "parameters": run["parameters"]
            | {"comparative_from": "2026-04-01", "comparative_to": "2026-04-30"},
        },
    )
    target, comparison = await finish(app, client, created.json()["id"])
    summary = comparison["result"]["evidence"]["tax_summary"]
    assert summary["comparison_present"] and summary["ledger_count"] == 1
    assert summary["amounts"]["INR"]["credit"] == "20.0000"
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    job, download = await new_export(client, target, format_name)
    await finish(app, client, job["id"], "report-exports")
    grant = await client.get(download + "/download-token", headers=headers())
    output = await client.get(
        download + "/download", headers=headers(), params={"token": grant.json()["token"]}
    )
    assert output.status_code == 200
    if format_name == "CSV":
        rows = list(csv.DictReader(io.StringIO(output.content.decode("utf-8-sig"))))
        assert {row["Period"] for row in rows} == {"CURRENT", "COMPARATIVE"}
    else:
        assert "Current period; comparative rows" in output.text
