"""Native grouped statement and summary inputs have exact reference parity."""

import datetime as dt

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT
from test_native_ledger import prepared, request

from reports.domain.statements import calculate
from reports.queries.native_context import NativeContext
from reports.queries.native_statements import execute


@pytest.mark.parametrize(
    "code", ["TRIAL_BALANCE", "PROFIT_LOSS", "INCOME_EXPENSE", "BALANCE_SHEET", "ACCOUNT_SUMMARY"]
)
async def test_native_financial_groups_match_reference_across_years_comparatives_and_grains(
    app, code
):
    identities, facts, ids = await prepared(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            for values in (
                {"date_from": "2026-04-01", "date_to": "2026-04-30"},
                {
                    "date_from": "2027-04-01",
                    "date_to": "2027-04-30",
                    "comparative_from": "2026-04-01",
                    "comparative_to": "2026-04-30",
                },
                {"date_from": "2026-04-02", "date_to": "2027-04-30"},
                {"date_from": "2026-04-03", "date_to": "2026-04-03"},
            ):
                for grain in ("DAY", "MONTH") if code == "ACCOUNT_SUMMARY" else (None,):
                    query = request(
                        identities[2], code, **values, **({"grain": grain} if grain else {})
                    )
                    actual = await execute(db, context, query, 100000)
                    assert actual == calculate(facts, query, dt.date(2026, 4, 1))
            with pytest.raises(ConflictError, match="bound"):
                await execute(db, context, request(identities[2], code), 1)


async def test_native_summary_currency_account_filters_and_empty_months(app):
    identities, facts, ids = await prepared(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            for values in (
                {"account_id": ids["cash"]},
                {"basis": "TRANSACTION", "currency": "INR"},
                {"basis": "TRANSACTION", "currency": "USD"},
                {"date_from": "2026-06-05", "date_to": "2026-06-20"},
            ):
                query = request(identities[2], "ACCOUNT_SUMMARY", grain="MONTH", **values)
                assert await execute(db, context, query, 100000) == calculate(
                    facts, query, context.coverage
                )


async def test_native_party_summary_keeps_validated_party_and_quiet_carry(app, client):
    import uuid

    from billing_platform.errors import ValidationFailedError
    from conftest import headers
    from test_framework_execution import proof

    from reports.tasks.framework_worker import process

    identities, facts, ids = await prepared(app)
    party = next(str(row.source_id) for row in facts if row.entity == "party")
    parameters = {
        "date_from": "2026-06-05",
        "date_to": "2026-06-06",
        "grain": "MONTH",
        "party_id": party,
    }
    query = request(identities[2], "ACCOUNT_SUMMARY", **parameters)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            rows, _ = await execute(db, context, query, 100000)
            assert rows == calculate(facts, query, context.coverage)[0]
            assert len(rows) == 2
            assert all(row["opening"] == row["closing"] == "80.0000" for row in rows)
            with pytest.raises(ValidationFailedError):
                await execute(
                    db, context, query.model_copy(update={"party_id": uuid.uuid4()}), 100000
                )
            with pytest.raises(ConflictError, match="bound"):
                await execute(db, context, query, 1)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    path = f"/v2/companies/{COMPANY}/report-runs"
    created = await client.post(
        path,
        headers=headers(),
        json={
            "code": "ACCOUNT_SUMMARY",
            "generation_id": str(identities[2]),
            "parameters": parameters,
        },
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
    result = await client.get(path + "/" + created.json()["id"], headers=headers())
    assert result.json()["status"] == "COMPLETE", result.text
    assert result.json()["attempt"] == 1


@pytest.mark.parametrize("code", ["TRIAL_BALANCE", "ACCOUNT_SUMMARY"])
async def test_native_calculations_publish_bounded_batches_through_v2(app, client, code):
    import uuid

    from conftest import headers
    from test_framework_execution import proof

    from reports.tasks.framework_worker import process

    identities, facts, ids = await prepared(app)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    app.state.settings.reference_fact_limit = 1
    path = f"/v2/companies/{COMPANY}/report-runs"
    body = {
        "code": code,
        "generation_id": str(identities[2]),
        "parameters": {"date_from": "2026-04-01", "date_to": "2026-04-30"},
    }
    response = await client.post(path, headers=headers(), json=body)
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
    assert result.json()["result"]["plan"]["key"] == "native_financial"
    assert result.json()["result"]["content_hash"]
    values, cursor = [], None
    while True:
        page = await client.get(
            target + "/rows",
            headers=headers(),
            params={"limit": 200, **({"cursor": cursor} if cursor else {})},
        )
        assert page.status_code == 200, page.text
        values.extend(row["data"] for row in page.json()["items"])
        cursor = page.json()["page"]["next_cursor"]
        if cursor is None:
            break
    if code == "TRIAL_BALANCE":
        from financial_fixture import financial_manifest

        from reports.tasks.report_catalog import catalog

        expected, evidence = (
            catalog()
            .resolve(code)
            .handler.execute(
                facts, identities[2], body["parameters"], financial_manifest(facts).control
            )
        )
    else:
        expected, evidence = calculate(
            facts, request(identities[2], code, **body["parameters"]), dt.date(2026, 4, 1)
        )
    assert values == expected
    assert result.json()["result"]["evidence"] == evidence
