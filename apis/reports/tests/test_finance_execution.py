"""Each Finance view runs through admission, worker, rows and private artifacts."""

import csv
import io
import uuid
import zipfile

import pytest
from conftest import COMPANY, TENANT, headers
from pypdf import PdfReader
from test_framework_execution import proof
from test_invoice_reports import component_dataset, purchase_dataset
from test_money_reports import bank_dataset
from test_native_bank import fixture as bank_source
from test_native_invoices import prepared as invoice_source
from test_native_ledger import prepared as ledger_source

from reports.domain.reporting.finance_views import FINANCE_VIEWS
from reports.tasks.framework_worker import process
from reports.tasks.report_catalog import catalog


@pytest.mark.parametrize("code", FINANCE_VIEWS)
async def test_finance_report_views_rows_drilldowns_and_exports(app, client, tmp_path, code):
    bank = code.startswith("BANK_RECONCILIATION") or code in {
        "PAYMENT_REGISTER",
        "RECEIPT_REGISTER",
    }
    invoice = code in {
        "SALES_REGISTER",
        "PURCHASE_REGISTER",
        "INVOICE_COMPONENT_REGISTER",
        "INVOICE_SETTLEMENT_REGISTER",
    }
    if bank:
        identities, _, _, parameters = await bank_source(app, code)
    else:
        if code == "BANK_BOOK":
            identities, _, _ = await ledger_source(app, dataset=bank_dataset())
        elif code == "PURCHASE_REGISTER":
            facts, ids, *_ = purchase_dataset()
            identities, _, _ = await ledger_source(app, dataset=(facts, ids))
        elif code == "INVOICE_COMPONENT_REGISTER":
            facts, ids, _ = component_dataset()
            identities, _, _ = await ledger_source(app, dataset=(facts, ids))
        else:
            identities, _, _ = await (invoice_source(app) if invoice else ledger_source(app))
        parameters = {"date_from": "2026-04-01", "date_to": "2027-04-30"}
        if code == "ACCOUNT_SUMMARY":
            parameters["grain"] = "MONTH"
            parameters["date_to"] = "2026-04-30"
        if code in {"OUTSTANDING_BILLS", "ADVANCES", "AGING", "INVOICE_SETTLEMENT_REGISTER"}:
            parameters.pop("date_from")
    settings = app.state.settings
    settings.framework_enabled = settings.native_queries_enabled = settings.exports_enabled = True
    settings.artifact_root = tmp_path / "private"
    endpoint = f"/v2/companies/{COMPANY}/report-runs"

    async def authority(job):
        return proof(job)

    async def execute(identity):
        await process(
            app.state.session_factory, settings, TENANT, COMPANY, uuid.UUID(identity), authority
        )

    for view in catalog().resolve(code).definition.views:
        response = await client.post(
            endpoint,
            headers=headers(),
            json={
                "code": code,
                "generation_id": str(identities[2]),
                "parameters": parameters,
                "view": view.key,
            },
        )
        assert response.status_code == 202, response.text
        identity = response.json()["id"]
        await execute(identity)
        target = endpoint + "/" + identity
        detail = (await client.get(target, headers=headers())).json()
        assert detail["status"] == "COMPLETE", detail
        result = (await client.get(target + "/rows?limit=200", headers=headers())).json()
        assert result["page"]["next_cursor"] is None
        rows = result["items"]
        assert rows, code
        if view.key == "party_balances":
            assert all(row["data"]["account_name"] for row in rows)
        if code == "INCOME_EXPENSE":
            kinds = {row["data"]["row_kind"] for row in rows}
            assert "NET_SURPLUS_DEFICIT" in kinds and "GROSS_PROFIT" not in kinds
        links = [
            link for row in rows for link in row.get("drilldowns", []) if link["method"] == "POST"
        ]
        if links:
            child = await client.post(
                target + "/drilldowns", headers=headers(), json={"token": links[0]["token"]}
            )
            assert child.status_code == 202, child.text
            await execute(child.json()["id"])
            child_detail = (
                await client.get(endpoint + "/" + child.json()["id"], headers=headers())
            ).json()
            assert child_detail["status"] == "COMPLETE", child_detail
        for format_name in ("CSV", "PDF", "XLSX"):
            exported = await client.post(
                target + "/exports",
                headers=headers(),
                json={"format": format_name, "view": view.key},
            )
            assert exported.status_code == 202, exported.text
            export_id = exported.json()["id"]
            await execute(export_id)
            artifact = f"/v2/companies/{COMPANY}/report-exports/{export_id}"
            token = await client.get(artifact + "/download-token", headers=headers())
            assert token.status_code == 200, token.text
            content = await client.get(
                artifact + "/download", headers=headers(), params={"token": token.json()["token"]}
            )
            assert content.status_code == 200
            if format_name == "CSV":
                parsed = list(csv.reader(io.StringIO(content.content.decode("utf-8-sig"))))
                assert parsed[0] == [column.title for column in view.columns]
                assert len(parsed) - 1 == len(rows)
            elif format_name == "PDF":
                assert content.content.startswith(b"%PDF")
                if code in {"BANK_RECONCILIATION", "INVOICE_SETTLEMENT_REGISTER"}:
                    assert (
                        "As of " in PdfReader(io.BytesIO(content.content)).pages[0].extract_text()
                    )
            else:
                with zipfile.ZipFile(io.BytesIO(content.content)) as archive:
                    assert "xl/workbook.xml" in archive.namelist()
