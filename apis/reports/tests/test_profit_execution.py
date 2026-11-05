"""The registered P&L views publish their own complete, scoped result rows."""

import csv
import io
import uuid

from conftest import COMPANY, TENANT, headers
from test_foundation import generation, load
from test_framework_execution import proof

from reports.tasks.framework_worker import process


async def test_profit_views_run_and_publish_through_framework(
    app, client, prefix, tmp_path
) -> None:
    app.state.settings.framework_enabled = True
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    source = await generation(client, prefix)
    await load(app, source["id"])
    endpoint = f"/v2/companies/{COMPANY}/report-runs"

    for view, dates in (
        ("comparison", {}),
        ("default", {"comparative_from": "2026-04-01", "comparative_to": "2026-04-02"}),
    ):
        rejected = await client.post(
            endpoint,
            headers=headers(),
            json={
                "code": "PROFIT_LOSS",
                "version": 6,
                "generation_id": source["id"],
                "view": view,
                "parameters": {"date_from": "2026-04-01", "date_to": "2026-04-30", **dates},
            },
        )
        assert rejected.status_code == 422, rejected.text

    async def authority(job):
        return proof(job)

    for view, dates in (
        ("default", {}),
        (
            "comparison",
            {"comparative_from": "2026-04-01", "comparative_to": "2026-04-02"},
        ),
    ):
        created = await client.post(
            endpoint,
            headers=headers(),
            json={
                "code": "PROFIT_LOSS",
                "version": 6,
                "generation_id": source["id"],
                "view": view,
                "parameters": {
                    "date_from": "2026-04-01",
                    "date_to": "2026-04-30",
                    "show_zero": False,
                    **dates,
                },
            },
        )
        assert created.status_code == 202, created.text
        identity = uuid.UUID(created.json()["id"])
        await process(
            app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
        )
        completed = await client.get(endpoint + "/" + str(identity), headers=headers())
        assert completed.status_code == 200, completed.text
        result = completed.json()
        assert result["status"] == "COMPLETE", result
        assert result["view"] == view
        assert (
            result["result"]["evidence"]["profit_summary"]["totals"]["NET_PROFIT"]["current"]
            == "0.0000"
        )
        page = await client.get(endpoint + "/" + str(identity) + "/rows", headers=headers())
        assert page.status_code == 200, page.text
        rows = [item["data"] for item in page.json()["items"]]
        assert [row["row_kind"] for row in rows] == [
            "SECTION",
            "SECTION",
            "GROSS_PROFIT",
            "SECTION",
            "SECTION",
            "NET_PROFIT",
        ]
        assert result["completed_rows"] == len(rows)
        if view == "default":
            queried = await client.post(
                endpoint + "/" + str(identity) + "/queries",
                headers=headers(),
                json={"q": "Direct"},
            )
            assert queried.status_code == 422, queried.text
        if view == "comparison":
            assert all("previous_amount" in row for row in rows)
        for format_name in ("CSV", "PDF"):
            exported = await client.post(
                endpoint + "/" + str(identity) + "/exports",
                headers=headers(),
                json={"format": format_name, "view": view},
            )
            assert exported.status_code == 202, exported.text
            export_id = uuid.UUID(exported.json()["id"])
            await process(
                app.state.session_factory, app.state.settings, TENANT, COMPANY, export_id, authority
            )
            target = f"/v2/companies/{COMPANY}/report-exports/{export_id}"
            token = await client.get(target + "/download-token", headers=headers())
            assert token.status_code == 200, token.text
            response = await client.get(
                target + "/download", headers=headers(), params={"token": token.json()["token"]}
            )
            assert response.status_code == 200, response.text
            if format_name == "CSV":
                exported_rows = list(
                    csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))
                )
                assert len(exported_rows) == len(rows)
                assert exported_rows[-1]["Account / group"] == "Net profit"
                assert exported_rows[-1]["Current"] == "0.0000"
                assert ("Previous" in exported_rows[-1]) == (view == "comparison")
            else:
                from pypdf import PdfReader

                content = "".join(
                    page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages
                ).replace("\ufb01", "fi")
                assert "Net profit" in content
                assert "Zero accounts" in content
                assert ("Previous" in content) == (view == "comparison")


async def test_native_comparison_keeps_prior_only_accounts_and_export_codes(
    app, client, tmp_path
) -> None:
    from test_native_ledger import prepared

    identities, _, _ = await prepared(app)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    endpoint = f"/v2/companies/{COMPANY}/report-runs"

    async def authority(job):
        return proof(job)

    created = await client.post(
        endpoint,
        headers=headers(),
        json={
            "code": "PROFIT_LOSS",
            "version": 6,
            "generation_id": str(identities[2]),
            "view": "comparison",
            "parameters": {
                "date_from": "2027-04-01",
                "date_to": "2027-04-30",
                "comparative_from": "2026-04-01",
                "comparative_to": "2026-04-30",
                "show_zero": False,
            },
        },
    )
    assert created.status_code == 202, created.text
    identity = uuid.UUID(created.json()["id"])
    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
    )
    completed = await client.get(endpoint + "/" + str(identity), headers=headers())
    assert completed.status_code == 200, completed.text
    result = completed.json()
    assert result["status"] == "COMPLETE", result
    totals = result["result"]["evidence"]["profit_summary"]["totals"]
    assert totals["NET_PROFIT"] == {"current": "0.0000", "previous": "160.0000"}
    page = await client.get(endpoint + "/" + str(identity) + "/rows", headers=headers())
    assert page.status_code == 200, page.text
    rows = [item["data"] for item in page.json()["items"]]
    account = next(
        row for row in rows if row["row_kind"] == "ACCOUNT" and row["previous_amount"] != "0.0000"
    )
    group = next(row for row in rows if row["row_kind"] == "GROUP")
    assert account["amount"] == "0.0000"
    assert group["code"] == group["group_code"]
    assert account["code"] == account["account_code"]
    export = await client.post(
        endpoint + "/" + str(identity) + "/exports",
        headers=headers(),
        json={"format": "CSV", "view": "comparison"},
    )
    assert export.status_code == 202, export.text
    export_id = uuid.UUID(export.json()["id"])
    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, export_id, authority
    )
    target = f"/v2/companies/{COMPANY}/report-exports/{export_id}"
    token = await client.get(target + "/download-token", headers=headers())
    assert token.status_code == 200, token.text
    output = await client.get(
        target + "/download", headers=headers(), params={"token": token.json()["token"]}
    )
    assert output.status_code == 200, output.text
    exported = list(csv.DictReader(io.StringIO(output.content.decode("utf-8-sig"))))
    assert any(
        row["Account / group"] == group["label"] and row["Code"] == group["group_code"]
        for row in exported
    )
    assert any(
        row["Account / group"] == account["label"] and row["Code"] == account["account_code"]
        for row in exported
    )
