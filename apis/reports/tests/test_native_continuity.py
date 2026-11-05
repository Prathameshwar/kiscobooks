"""Native source parity, API scope, signed drilldowns and immutable query/export support."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT, headers
from test_framework_execution import proof
from test_native_ledger import prepared, request

from reports.domain.statements import calculate
from reports.queries.native_context import NativeContext
from reports.queries.native_continuity import execute
from reports.tasks.framework_worker import process


async def test_native_continuity_has_reference_parity_and_bounded_results(app):
    identities, facts, _ = await prepared(app)
    query = request(
        identities[2], "BALANCE_CONTINUITY", date_from="2027-04-01", date_to="2028-03-31"
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            actual, evidence = await execute(db, context, query, 100000)
            expected, expected_evidence = calculate(facts, query, context.coverage)
            assert len(actual) == len(expected)
            for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
                assert left == right, (
                    index,
                    {
                        key: (left.get(key), right.get(key))
                        for key in left.keys() | right.keys()
                        if left.get(key) != right.get(key)
                    },
                )
            assert evidence == expected_evidence
            with pytest.raises(ConflictError, match="bound"):
                await execute(db, context, query, 2)


async def test_continuity_api_is_scoped_idempotent_searchable_and_has_carried_bill_drilldown(
    app, client, tmp_path
):
    identities, _facts, _ = await prepared(app)
    app.state.settings.framework_enabled = app.state.settings.native_queries_enabled = True
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    path = f"/v2/companies/{COMPANY}/report-runs"
    body = {
        "code": "BALANCE_CONTINUITY",
        "generation_id": str(identities[2]),
        "parameters": {"date_from": "2027-04-01", "date_to": "2028-03-31"},
    }
    assert (await client.post(path, json=body)).status_code == 401
    assert (
        await client.post(path, headers=headers(permissions=frozenset({"report.read"})), json=body)
    ).status_code == 403
    foreign = uuid.uuid4()
    wrong = await client.post(
        f"/v2/companies/{foreign}/report-runs", headers=headers(company=foreign), json=body
    )
    assert wrong.status_code == 403, wrong.text
    key = headers()
    created = await client.post(path, headers=key, json=body)
    assert created.status_code == 202, created.text
    assert (await client.post(path, headers=key, json=body)).json()["id"] == created.json()["id"]

    async def authority(job):
        return proof(job)

    async def finish(identity):
        await process(
            app.state.session_factory,
            app.state.settings,
            TENANT,
            COMPANY,
            uuid.UUID(identity),
            authority,
        )

    identity = created.json()["id"]
    await finish(identity)
    result = await client.get(path + "/" + identity, headers=headers())
    assert result.json()["status"] == "COMPLETE", result.text
    first = await client.get(path + "/" + identity + "/rows?limit=2", headers=headers())
    assert first.status_code == 200 and len(first.json()["items"]) == 2
    assert first.json()["items"][0]["data"]["reconciled"] is True
    assert first.json()["page"]["next_cursor"]
    page = await client.get(path + "/" + identity + "/rows?limit=50", headers=headers())
    bill = next(row for row in page.json()["items"] if row["data"]["row_kind"] == "BILL_CONTINUITY")
    link = next(link for link in bill["drilldowns"] if link["key"] == "party_bills")
    child = await client.post(
        path + "/" + identity + "/drilldowns", headers=headers(), json={"token": link["token"]}
    )
    assert child.status_code == 202, child.text
    assert child.json()["parameters"]["date_to"] == "2027-03-31"
    filtered = await client.post(
        path + "/" + identity + "/queries",
        headers=headers(),
        json={"q": "CASH", "sort": "account_code"},
    )
    assert filtered.status_code == 202, filtered.text
    await finish(filtered.json()["id"])
    selected = await client.get(path + "/" + filtered.json()["id"] + "/rows", headers=headers())
    assert selected.status_code == 200, selected.text
    assert {row["data"].get("account_code") for row in selected.json()["items"]} == {"CASH"}
    exported = await client.post(
        path + "/" + identity + "/exports", headers=headers(), json={"format": "CSV"}
    )
    assert exported.status_code == 202, exported.text
    await finish(exported.json()["id"])
    target = f"/v2/companies/{COMPANY}/report-exports/{exported.json()['id']}"
    detail = await client.get(target, headers=headers())
    assert detail.json()["status"] == "COMPLETE", detail.text
    grant = await client.get(target + "/download-token", headers=headers())
    assert grant.status_code == 200, grant.text
    output = await client.get(
        target + "/download", headers=headers(), params={"token": grant.json()["token"]}
    )
    assert output.status_code == 200 and "Next Opening" in output.text
