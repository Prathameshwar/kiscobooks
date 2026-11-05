"""Native bank and tender components preserve reconciliation and register behavior."""

import datetime as dt
import uuid

import pytest
from bank_evidence_fixture import evidence_dataset
from billing_platform.db import tenant_scope
from conftest import COMPANY, TENANT, headers
from fixtures import source
from test_framework_execution import proof
from test_money_reports import bank_dataset
from test_native_ledger import prepared, request

from reports.domain.statements import calculate
from reports.queries.native_bank import CODES, TENDERS, execute
from reports.queries.native_context import NativeContext
from reports.tasks.framework_worker import process


async def fixture(app, code):
    if code in {"BANK_RECONCILIATION_EVIDENCE", "BANK_RECONCILIATION_WORKLIST"}:
        facts, original, ids = evidence_dataset()
        parameters = {
            "account_id": ids["cash"],
            "basis": "TRANSACTION",
            "currency": "INR",
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
        }
        if code == "BANK_RECONCILIATION_EVIDENCE":
            parameters["session_id"] = ids["session"]
    else:
        facts, ids = bank_dataset()
        parameters = {"date_from": "2026-04-01", "date_to": "2027-04-30"}
        if code == "BANK_RECONCILIATION":
            parameters.pop("date_from")
            parameters |= {"account_id": ids["cash"], "statement_balance": "100"}
        else:
            facts = [
                source(row.entity, row.source_id, row.data | {"kind": "PAYMENT"})
                if row.entity == "journal" and row.data["number"] == "expense"
                else row
                for row in facts
            ]
    identities, facts, ids = await prepared(app, dataset=(facts, ids))
    return identities, facts, ids, parameters


@pytest.mark.parametrize("code", sorted(CODES))
async def test_native_bank_and_tender_grains_match_reference(app, code):
    identities, facts, ids, parameters = await fixture(app, code)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            variations = [{}]
            if code in TENDERS:
                variations += [
                    {"account_id": ids["cash"]},
                    {"role": "CUSTOMER"},
                    {"comparative_from": "2026-04-01", "comparative_to": "2026-04-30"},
                    {"date_from": "2027-04-01"},
                    {"basis": "TRANSACTION", "currency": "USD"},
                ]
            if code == "BANK_RECONCILIATION":
                variations += [{"statement_balance": "90"}, {"date_from": "2027-04-01"}]
            if code == "BANK_RECONCILIATION_WORKLIST":
                variations += [{"date_from": "2027-04-01", "date_to": "2027-04-30"}]
            for extra in variations:
                query = request(identities[2], code, **(parameters | extra))
                actual = await execute(db, context, query, 100000)
                assert actual == calculate(facts, query, context.coverage)
            assert (await execute(db, context, request(identities[2], code, **parameters), 100000))[
                0
            ]


@pytest.mark.parametrize("code", sorted(CODES))
async def test_native_bank_v2_runs_above_reference_admission(app, client, code):
    identities, facts, ids, parameters = await fixture(app, code)
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
    page = await client.get(target + "/rows", headers=headers(), params={"limit": 200})
    expected, evidence = calculate(
        facts, request(identities[2], code, **parameters), dt.date(2026, 4, 1)
    )
    assert [row["data"] for row in page.json()["items"]] == expected
    if code in TENDERS:
        count, amount = (1, "40.0000") if code == "PAYMENT_REGISTER" else (2, "150.0000")
        evidence["book_summary"] = {
            "code": code,
            "record_count": count,
            "entry_count": count,
            "voucher_count": count,
            "instrument_count": count,
            "amounts": {"INR": {"amount": amount}},
        }
    assert result.json()["result"]["evidence"] == evidence
