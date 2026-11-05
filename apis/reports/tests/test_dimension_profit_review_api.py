"""Native source and exported-selection regressions for profit review."""

import io
import unicodedata

import pytest
from billing_platform.db import tenant_scope
from conftest import COMPANY, TENANT, headers
from pypdf import PdfReader
from test_analytics_api import BASE, PARAMS, complete
from test_dimension_profit_api import profit_dataset
from test_native_ledger import prepared

from reports.queries.native_context import NativeContext
from reports.tasks.analytics_source import documents


async def test_disjoint_profit_periods_do_not_load_invoices_in_the_gap(app):
    identities, _, _ = await prepared(app, dataset=profit_dataset())
    # The only invoice is posted on April 2, between these two selected periods.
    values = {
        "date_from": "2026-04-03",
        "date_to": "2026-04-30",
        "comparative_from": "2026-04-01",
        "comparative_to": "2026-04-01",
    }
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            assert await documents(db, context, values, 10) == []
            # Customer-history callers still deliberately read the intervening activity.
            assert len(await documents(db, context, values, 10, history=True)) == 1


@pytest.mark.parametrize("code", ["BUYER_PROFIT", "PRODUCT_PROFIT"])
async def test_native_profit_retains_named_selection_even_when_no_rows_match(
    app, client, tmp_path, code
):
    identities, facts, ids = await prepared(app, dataset=profit_dataset())
    party = str(next(row.source_id for row in facts if row.entity == "party"))
    app.state.settings.framework_enabled = app.state.settings.native_queries_enabled = True
    parameters = PARAMS | {"party_id": party, "currency": "INR", "search": "no matching activity"}
    if code == "PRODUCT_PROFIT":
        parameters |= {"item_id": ids["item"], "group_id": ids["child"]}
    response = await client.post(
        BASE + "/report-runs",
        headers=headers(),
        json={
            "code": code,
            "generation_id": str(identities[2]),
            "parameters": parameters,
        },
    )
    assert response.status_code == 202, response.text
    await complete(app, response.json()["id"])
    job = (
        await client.get(BASE + "/report-runs/" + response.json()["id"], headers=headers())
    ).json()
    assert job["status"] == "COMPLETE", job
    selected = job["result"]["evidence"]["analytics"]["selected_filters"]
    assert "Buyer" in selected["party_id"] and party in selected["party_id"]
    assert selected["currency"] == "INR"
    if code == "PRODUCT_PROFIT":
        assert "Item" in selected["item_id"] and ids["item"] in selected["item_id"]
        assert "Child" in selected["group_id"] and ids["child"] in selected["group_id"]
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    exported = await client.post(
        BASE + "/report-runs/" + job["id"] + "/exports", headers=headers(), json={"format": "PDF"}
    )
    assert exported.status_code == 202, exported.text
    await complete(app, exported.json()["id"])
    export_path = BASE + "/report-exports/" + exported.json()["id"]
    token = (await client.get(export_path + "/download-token", headers=headers())).json()["token"]
    download = await client.get(
        export_path + "/download", headers=headers(), params={"token": token}
    )
    assert download.status_code == 200, download.text[:100]
    rendered = " ".join(
        unicodedata.normalize(
            "NFKC",
            " ".join(page.extract_text() for page in PdfReader(io.BytesIO(download.content)).pages),
        ).split()
    )
    assert "Buyer: " + selected["party_id"] in rendered
    if code == "PRODUCT_PROFIT":
        assert "Product group: " + selected["group_id"] in rendered
        assert "Product: " + selected["item_id"] in rendered
