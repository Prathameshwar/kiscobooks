"""Dated native settlement aggregates must match bill and aging financial rules exactly."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT, headers
from financial_fixture import financial_dataset
from fixtures import source
from test_framework_execution import proof
from test_native_ledger import prepared, request

from reports.domain.statements import calculate
from reports.queries.native_context import NativeContext
from reports.queries.native_open_items import CODES, execute
from reports.tasks.framework_worker import process


@pytest.mark.parametrize("invalid", [False, True])
async def test_native_open_items_reversals_and_overallocation_controls(app, invalid):
    facts, ids = financial_dataset()
    changed = False
    values = []
    for fact in facts:
        if (
            fact.entity == "allocation"
            and fact.data["posting_date"] == "2026-04-03"
            and not changed
        ):
            update = (
                {"amount": "400", "debt_base_amount": "400", "credit_base_amount": "400"}
                if invalid
                else {"reversal_date": "2026-04-05"}
            )
            fact = source(fact.entity, fact.source_id, fact.data | update)
            changed = True
        values.append(fact)
    identities, facts, _ = await prepared(app, dataset=(values, ids))
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            for date in ("2026-04-04", "2026-04-06", "2027-04-30"):
                query = request(identities[2], "OUTSTANDING_BILLS", date_to=date)
                if invalid and date == "2027-04-30":
                    with pytest.raises(ConflictError, match="allocations exceed"):
                        await execute(db, context, query, 100000)
                elif not invalid:
                    assert await execute(db, context, query, 100000) == calculate(
                        facts, query, context.coverage
                    )


async def test_native_open_item_scope_and_result_admission(app):
    identities, facts, _ = await prepared(app)
    await prepared(app, tenant=uuid.uuid4())
    await prepared(app, company=uuid.uuid4())
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            query = request(identities[2], "OUTSTANDING_BILLS", date_to="2026-04-30")
            assert await execute(db, context, query, 100000) == calculate(
                facts, query, context.coverage
            )
            for code in ("OUTSTANDING_BILLS", "AGING"):
                with pytest.raises(ConflictError, match="bound"):
                    await execute(db, context, query.model_copy(update={"code": code}), 0)


@pytest.mark.parametrize("code", sorted(CODES))
async def test_native_open_item_as_of_roles_currencies_and_allocations_match_reference(app, code):
    identities, facts, ids = await prepared(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            for values in (
                {"date_to": "2026-04-01"},
                {"date_to": "2026-04-02"},
                {"date_to": "2026-04-30"},
                {"date_to": "2026-06-01"},
                {"date_to": "2026-07-01"},
                {"date_to": "2026-08-01"},
                {"date_to": "2027-04-30"},
                {"role": "SUPPLIER"},
                {"account_id": ids["party"]},
                {"basis": "TRANSACTION", "currency": "INR"},
                {"basis": "TRANSACTION", "currency": "USD"},
            ):
                query = request(identities[2], code, date_from="2026-04-01", **values)
                assert await execute(db, context, query, 100000) == calculate(
                    facts, query, context.coverage
                )


@pytest.mark.parametrize("code", sorted(CODES))
async def test_native_open_items_execute_through_v2_without_loading_full_history(app, client, code):
    identities, facts, _ = await prepared(app)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    app.state.settings.reference_fact_limit = 1
    path = f"/v2/companies/{COMPANY}/report-runs"
    response = await client.post(
        path,
        headers=headers(),
        json={
            "code": code,
            "generation_id": str(identities[2]),
            "parameters": {"date_to": "2026-04-30"},
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
    page = await client.get(target + "/rows", headers=headers(), params={"limit": 200})
    from financial_fixture import financial_manifest

    from reports.tasks.report_catalog import catalog

    expected, evidence = (
        catalog()
        .resolve(code)
        .handler.execute(
            facts, identities[2], {"date_to": "2026-04-30"}, financial_manifest(facts).control
        )
    )
    assert [row["data"] for row in page.json()["items"]] == expected
    assert result.json()["result"]["evidence"] == evidence
