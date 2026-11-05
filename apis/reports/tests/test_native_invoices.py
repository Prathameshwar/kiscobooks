"""Native invoice queries preserve each register's frozen grain, order and dated rules."""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT, headers
from financial_fixture import financial_manifest
from invoice_fixture import invoice_dataset
from sqlalchemy import select
from test_framework_execution import proof
from test_invoice_reports import _append_credit_note
from test_native_ledger import request
from test_source_versions import staged

from reports.domain.invoice_registers import CODES
from reports.domain.statements import calculate
from reports.models.source_versions import ReportSourceCut
from reports.queries.native_context import NativeContext
from reports.queries.native_invoices import execute
from reports.tasks.framework_worker import process
from reports.tasks.source_publication import publish


async def prepared(app):
    facts, ids = invoice_dataset()
    for index in range(11):
        _append_credit_note(facts, ids, "1", f"CN-{index}")
    facts.sort(key=lambda row: (row.entity, str(row.source_id)))
    identities, _ = await staged(app, source=facts, control=financial_manifest(facts).control)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(
                    ReportSourceCut.company_id == COMPANY,
                    ReportSourceCut.generation_id == identities[2],
                )
            )
        await publish(app.state.session_factory, COMPANY, cut.id)
    return identities, facts, ids


@pytest.mark.parametrize("code", CODES)
async def test_invoice_components_match_reference_across_batch_and_date_boundaries(app, code):
    identities, facts, ids = await prepared(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            for values in (
                {},
                {"invoice_id": ids["invoice"]},
                {
                    "date_from": "2027-04-01",
                    "comparative_from": "2026-04-01",
                    "comparative_to": "2026-04-30",
                },
                {"date_from": "2026-06-01", "date_to": "2026-06-30"},
                {"basis": "TRANSACTION", "currency": "USD"},
            ):
                query = request(identities[2], code, **values)
                actual = await execute(db, context, query, 100000)
                assert actual == calculate(facts, query, context.coverage)


async def test_invoice_native_result_bounds_and_v2_execution(app, client, monkeypatch):
    from reports.domain.book_summaries import summarize
    from reports.queries import native_invoices

    identities, facts, ids = await prepared(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            query = request(identities[2], "SALES_REGISTER")
            with pytest.raises(ConflictError, match="bound"):
                await execute(db, context, query, 1)
            with monkeypatch.context() as patch:
                patch.setattr(native_invoices, "RESULT_BYTES", 1)
                with pytest.raises(ConflictError, match="bound"):
                    await execute(db, context, query, 100000)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    app.state.settings.reference_fact_limit = 1
    path = f"/v2/companies/{COMPANY}/report-runs"
    parameters = {"date_from": "2026-04-01", "date_to": "2026-04-30"}
    response = await client.post(
        path,
        headers=headers(),
        json={
            "code": "SALES_REGISTER",
            "generation_id": str(identities[2]),
            "parameters": parameters,
        },
    )
    assert response.status_code == 202, response.text
    identity = uuid.UUID(response.json()["id"])

    async def authority(job):
        return proof(job)

    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
    )
    target = path + "/" + str(identity)
    result = await client.get(target, headers=headers())
    assert result.json()["status"] == "COMPLETE", result.text
    values = await client.get(target + "/rows", headers=headers(), params={"limit": 200})
    expected, evidence = calculate(
        facts, request(identities[2], "SALES_REGISTER", **parameters), dt.date(2026, 4, 1)
    )
    assert [row["data"] for row in values.json()["items"]] == expected
    assert result.json()["result"]["evidence"] == evidence | {
        "book_summary": summarize("SALES_REGISTER", expected)
    }
