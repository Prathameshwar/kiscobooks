import csv
import io
import json
import uuid
import zipfile

import pytest
from conftest import COMPANY, TENANT, headers
from test_framework_execution import proof
from test_native_ledger import prepared

from reports.tasks.framework_worker import process


@pytest.mark.parametrize("native", [False, True])
async def test_balance_views_execution_and_complete_exports(app, client, tmp_path, native):
    identities, _, _ = await prepared(app)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = native
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    endpoint = f"/v2/companies/{COMPANY}/report-runs"

    async def authority(job):
        return proof(job)

    for view, dates in (("default", {}), ("comparison", {"comparative_to": "2026-04-30"})):
        created = await client.post(
            endpoint,
            headers=headers(),
            json={
                "code": "BALANCE_SHEET",
                "version": 6,
                "view": view,
                "generation_id": str(identities[2]),
                "parameters": {"date_to": "2027-04-30", **dates},
            },
        )
        assert created.status_code == 202, created.text
        identity = uuid.UUID(created.json()["id"])
        await process(
            app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
        )
        result = (await client.get(endpoint + "/" + str(identity), headers=headers())).json()
        assert result["status"] == "COMPLETE", result
        summary = result["result"]["evidence"]["balance_summary"]
        assert summary["totals"]["ASSET"] == summary["totals"]["LIABILITIES_EQUITY"]
        assert summary["totals"]["EQUITY"]["current"] == "260.0000"
        rows = (
            await client.get(endpoint + "/" + str(identity) + "/rows", headers=headers())
        ).json()["items"]
        account = next(r for r in rows if r["data"]["row_kind"] == "ACCOUNT")
        assert any(link["key"] == "balance_account_entries" for link in account["drilldowns"])
        if view == "comparison":
            link = next(
                link
                for link in account["drilldowns"]
                if link["key"] == "balance_comparison_entries"
            )
            child = await client.post(
                endpoint + "/" + str(identity) + "/drilldowns",
                headers=headers(),
                json={"token": link["token"]},
            )
            assert child.status_code == 202, child.text
            assert child.json()["parameters"]["date_to"] == "2026-04-30"
            assert child.json()["parameters"]["date_from"] == "2026-04-01"
        denied = await client.post(
            endpoint + "/" + str(identity) + "/queries", headers=headers(), json={"q": "Cash"}
        )
        assert denied.status_code == 422
        if view == "default":
            for output in ("PDF", "HTML"):
                package = await client.post(
                    endpoint + "/" + str(identity) + "/exports",
                    headers=headers(),
                    json={"format": output, "view": view, "delivery": "PACKAGE", "part_rows": 1},
                )
                assert package.status_code == 422, package.text
        for format_name in ("CSV", "PDF", "HTML", "XLSX"):
            response = await client.post(
                endpoint + "/" + str(identity) + "/exports",
                headers=headers(),
                json={"format": format_name, "view": view},
            )
            assert response.status_code == 202, response.text
            export_id = uuid.UUID(response.json()["id"])
            await process(
                app.state.session_factory, app.state.settings, TENANT, COMPANY, export_id, authority
            )
            target = f"/v2/companies/{COMPANY}/report-exports/{export_id}"
            token = await client.get(target + "/download-token", headers=headers())
            assert token.status_code == 200, token.text
            download = await client.get(
                target + "/download", headers=headers(), params={"token": token.json()["token"]}
            )
            assert download.status_code == 200, download.text
            if format_name == "CSV":
                values = list(csv.DictReader(io.StringIO(download.content.decode("utf-8-sig"))))
                assert len(values) == len(rows)
                assert values[-1]["Current"] == summary["totals"]["LIABILITIES_EQUITY"]["current"]
            elif format_name == "PDF":
                from pypdf import PdfReader

                text = " ".join(
                    " ".join(
                        p.extract_text() for p in PdfReader(io.BytesIO(download.content)).pages
                    ).split()
                )
                assert "As at" in text and "Total liabilities and equity" in text
                assert ("Previous" in text) == (view == "comparison")
            elif format_name == "HTML":
                assert "As at" in download.text and "Total liabilities and equity" in download.text
            else:
                with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
                    assert "xl/workbook.xml" in archive.namelist()
        if view == "comparison":
            response = await client.post(
                endpoint + "/" + str(identity) + "/exports",
                headers=headers(),
                json={"format": "HTML", "view": view, "delivery": "PACKAGE", "part_rows": 3},
            )
            assert response.status_code == 202, response.text
            export_id = uuid.UUID(response.json()["id"])
            await process(
                app.state.session_factory, app.state.settings, TENANT, COMPANY, export_id, authority
            )
            target = f"/v2/companies/{COMPANY}/report-exports/{export_id}"
            token = await client.get(target + "/download-token", headers=headers())
            assert token.status_code == 200, token.text
            download = await client.get(
                target + "/download", headers=headers(), params={"token": token.json()["token"]}
            )
            assert download.status_code == 200
            with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                assert manifest["row_count"] == len(rows)
                assert sum(part["row_count"] for part in manifest["parts"]) == len(rows)
                assert len(manifest["parts"]) > 1


async def test_balance_rejects_incompatible_view_and_dates(app, client):
    app.state.settings.framework_enabled = True
    for view, parameters in (
        ("comparison", {"date_to": "2027-04-30"}),
        ("default", {"date_to": "2027-04-30", "comparative_to": "2026-04-30"}),
        ("comparison", {"date_to": "2027-04-30", "comparative_to": "2027-05-01"}),
        ("default", {"date_to": "2027-04-30", "account_id": str(uuid.uuid4())}),
    ):
        response = await client.post(
            f"/v2/companies/{COMPANY}/report-runs",
            headers=headers(),
            json={
                "code": "BALANCE_SHEET",
                "version": 6,
                "view": view,
                "generation_id": str(uuid.uuid4()),
                "parameters": parameters,
            },
        )
        assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "view,dates",
    [
        ("default", {"date_to": "2026-03-31"}),
        ("comparison", {"date_to": "2027-03-31", "comparative_to": "2026-03-31"}),
    ],
)
async def test_unavailable_history_is_rejected_before_queueing(app, client, view, dates):
    identities, _, _ = await prepared(app)
    app.state.settings.framework_enabled = True
    response = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(),
        json={
            "code": "BALANCE_SHEET",
            "version": 6,
            "view": view,
            "generation_id": str(identities[2]),
            "parameters": dates,
        },
    )
    assert response.status_code == 422, response.text
    assert "history" in response.text.lower()
    history = await client.get(
        f"/v2/companies/{COMPANY}/report-runs?code=BALANCE_SHEET", headers=headers()
    )
    assert history.status_code == 200, history.text
    assert history.json()["items"] == []
