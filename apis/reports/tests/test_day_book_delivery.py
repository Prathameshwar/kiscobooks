"""Day Book API → verified worker → bounded results → private export."""

import csv
import io
import uuid
import zipfile
from decimal import Decimal

import pytest
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from financial_fixture import financial_dataset
from test_framework_execution import proof
from test_native_ledger import prepared

from reports.tasks.framework_worker import process


async def authority(job):
    return proof(job)


@pytest.mark.parametrize("format_name", ["CSV", "XLSX", "PDF"])
@pytest.mark.parametrize("view", ["default", "accounting"])
async def test_verified_day_book_rows_summary_and_private_complete_export(
    app, client, tmp_path, format_name, view
):
    facts, ids = financial_dataset()
    # The source helper links its first two journals. Keep both inside this period
    # rather than depending on random UUID ordering and occasionally linking 2027.
    facts.sort(key=lambda row: row.entity == "journal" and row.data["posting_date"] > "2026-04-30")
    identities, _facts, _ids = await prepared(app, dataset=(facts, ids))
    app.state.settings.framework_enabled = True
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    path = f"/v2/companies/{COMPANY}/report-runs"
    body = {
        "code": "DAY_BOOK_ACTIVITY",
        "generation_id": str(identities[2]),
        "view": view,
        "parameters": {
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
            "mode": "ACCOUNTING" if view == "accounting" else "VOUCHERS",
        },
    }
    token = headers()
    created = await client.post(path, headers=token, json=body)
    assert created.status_code == 202, created.text
    assert (await client.post(path, headers=token, json=body)).json()["id"] == created.json()["id"]
    identity = uuid.UUID(created.json()["id"])
    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
    )
    run = path + "/" + str(identity)
    detail = (await client.get(run, headers=headers())).json()
    assert detail["status"] == "COMPLETE", detail
    summary = detail["result"]["evidence"]["day_book"]
    assert summary["voucher_count"] == 3  # Two journals share one source voucher.
    assert summary["journal_count"] == 4
    assert summary["line_count"] == 8
    assert summary["debit"] == summary["credit"] == "460.0000"
    first = await client.get(run + "/rows?limit=1", headers=headers())
    assert first.status_code == 200, first.text
    assert len(first.json()["items"]) == 1
    assert first.json()["page"]["next_cursor"]
    assert (await client.get(run + "/rows")).status_code == 401
    assert (await client.get(run, headers=headers(user=uuid.uuid4()))).status_code == 403
    revoked = headers(permissions=PERMISSIONS - {"ledger.read"})
    assert (await client.get(run + "/rows", headers=revoked)).status_code == 403
    export_headers = headers()
    export_body = {"format": format_name, "view": view, "delivery": "SINGLE"}
    requested = await client.post(run + "/exports", headers=export_headers, json=export_body)
    assert requested.status_code == 202, requested.text
    exported = requested.json()
    replay = await client.post(run + "/exports", headers=export_headers, json=export_body)
    assert replay.json()["id"] == exported["id"]
    target = f"/v2/companies/{COMPANY}/report-exports/{exported['id']}"
    expected_rows = 8 if view == "accounting" else 4
    assert detail["completed_rows"] == expected_rows
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(exported["id"]),
        authority,
    )
    export_detail = (await client.get(target, headers=headers())).json()
    assert export_detail["status"] == "COMPLETE", export_detail
    assert export_detail["completed_rows"] == expected_rows
    grant = await client.get(target + "/download-token", headers=headers())
    assert grant.status_code == 200, grant.text
    output = await client.get(
        target + "/download", headers=headers(), params={"token": grant.json()["token"]}
    )
    assert output.status_code == 200, output.text
    if format_name == "CSV":
        rows = list(csv.DictReader(io.StringIO(output.content.decode("utf-8-sig"))))
        assert len(rows) == expected_rows  # The download includes every retained row.
        assert ("Account" in rows[0]) == (view == "accounting")
        assert sum((Decimal(row["Debit"]) for row in rows), Decimal(0)) == Decimal("460")
        assert sum((Decimal(row["Credit"]) for row in rows), Decimal(0)) == Decimal("460")
    else:
        if format_name == "XLSX":
            with zipfile.ZipFile(io.BytesIO(output.content)) as archive:
                sheet = archive.read("xl/worksheets/sheet1.xml").decode()
                assert sheet.count("<row ") == expected_rows + 1
                text = "".join(
                    archive.read(name).decode()
                    for name in archive.namelist()
                    if name.startswith("xl/worksheets/") and name.endswith(".xml")
                )
                if "xl/sharedStrings.xml" in archive.namelist():
                    text += archive.read("xl/sharedStrings.xml").decode()
        else:
            from pypdf import PdfReader

            text = "".join(
                page.extract_text() for page in PdfReader(io.BytesIO(output.content)).pages
            )
        for label in ("Day Book", "Vouchers", "Journal postings", "Accounting lines", "460.00"):
            assert label in text
    assert (
        await client.get(
            target + "/download-token", headers=headers(permissions=PERMISSIONS - {"ledger.read"})
        )
    ).status_code == 403
