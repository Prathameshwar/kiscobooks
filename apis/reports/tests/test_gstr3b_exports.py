import io
import json
import os
import uuid
import zipfile
from pathlib import Path

import pytest
from conftest import COMPANY, TENANT, headers
from test_framework_execution import proof
from test_gstr3b_api import GST, prepared

from reports.tasks.framework_worker import process


@pytest.mark.parametrize("export_format", ["PDF", "XLSX", "CSV"])
async def test_actual_statutory_artifacts_share_frozen_identity(
    app, client, tmp_path, export_format
):
    identity, frozen = await prepared(app, client, activity=True)
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    created = await client.post(
        f"/v2/companies/{COMPANY}/report-runs/{identity}/exports",
        headers=headers(registrations=GST),
        json={"format": export_format},
    )
    assert created.status_code == 202, created.text

    async def authority(job):
        return proof(job)

    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(created.json()["id"]),
        authority,
    )
    target = f"/v2/companies/{COMPANY}/report-exports/{created.json()['id']}"
    status = await client.get(target, headers=headers(registrations=GST))
    assert status.json()["status"] == "COMPLETE", status.text
    token = await client.get(target + "/download-token", headers=headers(registrations=GST))
    download = await client.get(
        target + "/download",
        headers=headers(registrations=GST),
        params={"token": token.json()["token"]},
    )
    assert download.status_code == 200, download.text[:100]
    if os.environ.get("GST_EXPORT_EVIDENCE_DIR"):
        destination = Path(os.environ["GST_EXPORT_EVIDENCE_DIR"])
        destination.mkdir(parents=True, exist_ok=True)
        (destination / ("preparation." + export_format.lower())).write_bytes(download.content)
        (destination / "preparation.json").write_text(json.dumps(frozen), encoding="utf-8")
        rows = await client.get(
            f"/v2/companies/{COMPANY}/report-runs/{identity}/gst-records",
            headers=headers(registrations=GST),
        )
        (destination / "rows.json").write_text(json.dumps(rows.json()), encoding="utf-8")
    if export_format == "PDF":
        assert download.content.startswith(b"%PDF")
        from pypdf import PdfReader

        text = "\n".join(
            page.extract_text() for page in PdfReader(io.BytesIO(download.content)).pages
        )
        assert "FORM GSTR-3B" in text
        assert "Calculation revision 1" in text
        assert GST[0]["number"] in text
        assert "6.1 Payment of tax" in text
        assert "Return preparation" in text
        assert "Prior-period liability breakup" in text
        assert text.index("3.2 Interstate") < text.index("4 Eligible ITC") < text.index("5 Exempt")
        assert text.index("4A1 Import of goods") < text.index("4B ITC reversed")
        assert "retained-source" in PdfReader(io.BytesIO(download.content)).pages[-1].extract_text()
    elif export_format == "XLSX":
        with zipfile.ZipFile(io.BytesIO(download.content)) as book:
            workbook = book.read("xl/workbook.xml").decode()
            for name in (
                "GSTR-3B form",
                "Table 3.2",
                "Table 6.1 payments",
                "Exceptions",
                "Reconciliation",
                "Prior period liability breakup",
            ):
                assert name in workbook
    else:
        assert "category" in download.text.lower() or "allocation" in download.text.lower()


async def test_statutory_export_rejects_generic_packages_and_html(app, client, tmp_path):
    identity, _ = await prepared(app, client, activity=True)
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    for body in ({"format": "HTML"}, {"format": "PDF", "delivery": "PACKAGE"}):
        response = await client.post(
            f"/v2/companies/{COMPANY}/report-runs/{identity}/exports",
            headers=headers(registrations=GST),
            json=body,
        )
        assert response.status_code == 422, response.text
