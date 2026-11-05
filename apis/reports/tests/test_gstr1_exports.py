import io
import json
import os
import uuid
import zipfile
from pathlib import Path

import pytest
from conftest import COMPANY, TENANT, headers
from test_framework_execution import proof
from test_gstr1_api import GSTR1_GST as GST
from test_gstr1_api import prepared
from test_gstr1_calculation import amendment, coverage, document

from reports.tasks.framework_worker import process


@pytest.mark.parametrize(
    ("export_format", "amended"),
    [("PDF", False), ("XLSX", False), ("CSV", False), ("CSV", True)],
)
async def test_actual_statutory_artifacts_share_frozen_identity(
    app, client, tmp_path, export_format, amended
):
    original = document(return_date="2026-08-01", document_date="2026-08-01")
    previous = amendment(original, "1100", "198", return_date="2026-09-01")
    revised = amendment(previous, "1200", "216")
    outward = [*coverage([revised], sequence=1), original, previous] if amended else None
    identity, frozen = await prepared(app, client, outward=outward)
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
    if os.environ.get("GSTR1_EXPORT_EVIDENCE_DIR") and not amended:
        destination = Path(os.environ["GSTR1_EXPORT_EVIDENCE_DIR"])
        destination.mkdir(parents=True, exist_ok=True)
        (destination / ("preparation." + export_format.lower())).write_bytes(download.content)
        (destination / "preparation.json").write_text(json.dumps(frozen), encoding="utf-8")
        rows = await client.get(
            f"/v2/companies/{COMPANY}/report-runs/{identity}/gstr1-records",
            headers=headers(registrations=GST),
        )
        (destination / "rows.json").write_text(json.dumps(rows.json()), encoding="utf-8")
    if export_format == "PDF":
        assert download.content.startswith(b"%PDF")
        from pypdf import PdfReader

        text = "\n".join(
            page.extract_text() for page in PdfReader(io.BytesIO(download.content)).pages
        )
        assert "FORM GSTR-1" in text
        assert GST[0]["number"] in text
        assert "Statutory table summary" in text
        assert "GSTR-3B bridge" in text
        assert "INV-1" in text
        assert "Verification" in text
        assert "Calculation revision 3" in text
    elif export_format == "XLSX":
        with zipfile.ZipFile(io.BytesIO(download.content)) as book:
            workbook = book.read("xl/workbook.xml").decode()
            for name in (
                "GSTR-1 summary",
                "Table 4A",
                "Table 12_B2B",
                "Table 13",
                "GSTR-3B bridge",
                "Readiness exceptions",
                "Reconciliation",
            ):
                assert name in workbook
    else:
        assert "document number" in download.text.lower() and "INV-1" in download.text
        if amended:
            assert original["id"] in download.text and previous["id"] in download.text
            assert "100.00" in download.text


async def test_statutory_export_rejects_generic_packages_and_html(app, client, tmp_path):
    identity, _ = await prepared(app, client)
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    for body in ({"format": "HTML"}, {"format": "PDF", "delivery": "PACKAGE"}):
        response = await client.post(
            f"/v2/companies/{COMPANY}/report-runs/{identity}/exports",
            headers=headers(registrations=GST),
            json=body,
        )
        assert response.status_code == 422, response.text
