"""Frozen branch reads must retain full controls and live company/field authority."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from sqlalchemy import select
from test_framework_execution import proof
from test_native_ledger import prepared

from reports.models.hierarchy import ReportHierarchyNode
from reports.tasks.framework_worker import process


async def completed(
    app,
    client,
    *,
    tenant=TENANT,
    company=COMPANY,
    version=6,
    generation=None,
    dataset=None,
    parameters=None,
):
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    if generation is None:
        identities, _, ids = await prepared(app, tenant=tenant, company=company, dataset=dataset)
        generation = str(identities[2])
    else:
        ids = {}
    path = f"/v2/companies/{company}/report-runs"
    body = {
        "code": "TRIAL_BALANCE",
        "version": version,
        "generation_id": generation,
        "parameters": {"date_from": "2026-04-02", "date_to": "2026-04-30"} | (parameters or {}),
    }
    auth = headers(tenant=tenant, company=company)
    response = await client.post(path, headers=auth, json=body)
    assert response.status_code == 202, response.text
    assert (await client.post(path, headers=auth, json=body)).json()["id"] == response.json()["id"]
    target = path + "/" + response.json()["id"]
    assert (await client.get(target + "/hierarchy", headers=auth)).status_code == 409

    async def authority(job):
        return proof(job)

    for _ in range(2):
        await process(
            app.state.session_factory,
            app.state.settings,
            tenant,
            company,
            uuid.UUID(response.json()["id"]),
            authority,
        )
    status = await client.get(target, headers=auth)
    assert status.json()["status"] == "COMPLETE", status.text
    return target, ids


async def test_hierarchy_branches_totals_cursors_and_signed_account_drilldown(app, client):
    target, _ = await completed(app, client)
    first = await client.get(target + "/hierarchy?limit=1", headers=headers())
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "no-store"
    body = first.json()
    assert body["items"][0]["data"]["row_kind"] == "HEAD"
    assert body["summary"]["closing_difference"] == "0.0000"
    assert type(body["summary"]["closing_debit"]) is str
    parent = body["items"][0]["data"]["node_key"]
    cursor = body["page"]["next_cursor"]
    assert cursor
    for changes in ({"parent": parent}, {"show_zero": False}, {"period": "COMPARATIVE"}):
        rejected = await client.get(
            target + "/hierarchy", headers=headers(), params={"cursor": cursor, **changes}
        )
        assert rejected.status_code == 422, rejected.text
    rows, parents = [], ["root"]
    while parents:
        selected, after = parents.pop(), None
        while True:
            result = await client.get(
                target + "/hierarchy",
                headers=headers(),
                params={"parent": selected, "limit": 1, **({"cursor": after} if after else {})},
            )
            assert result.status_code == 200, result.text
            page = result.json()
            assert page["summary"] == body["summary"]
            rows.extend(page["items"])
            parents.extend(
                row["data"]["node_key"] for row in page["items"] if row["data"]["child_count"]
            )
            after = page["page"]["next_cursor"]
            if not after:
                break
    accounts = [row for row in rows if row["data"]["row_kind"] == "ACCOUNT"]
    assert len(accounts) == body["summary"]["account_count"]
    assert all(row["drilldowns"] for row in accounts)
    link = next(link for link in accounts[0]["drilldowns"] if link["key"] != "row_detail")
    drilled = await client.post(
        target + "/drilldowns", headers=headers(), json={"token": link["token"]}
    )
    assert drilled.status_code == 202, drilled.text
    assert drilled.json()["code"] == "ACCOUNT_LEDGER"


async def test_hierarchy_authority_validation_and_legacy_readability(app, client):
    target, _ = await completed(app, client)
    endpoint = target + "/hierarchy"
    assert (await client.get(endpoint)).status_code == 401
    for auth in (
        headers(permissions=PERMISSIONS - {"report.read"}),
        headers(permissions=PERMISSIONS - {"accounting.account.read"}),
        headers(
            policies=[
                {"access": "read", "effect": "deny", "entity_type": "account", "field": "name"}
            ]
        ),
    ):
        assert (await client.get(endpoint, headers=auth)).status_code == 403
    foreign = uuid.uuid4()
    assert (
        await client.get(
            endpoint.replace(str(COMPANY), str(foreign)), headers=headers(company=foreign)
        )
    ).status_code == 403
    assert (await client.get(endpoint, headers=headers(tenant=foreign))).status_code == 404
    for params in (
        {"limit": 201},
        {"parent": "bad"},
        {"period": "UNKNOWN"},
        {"parent": "group:" + str(foreign)},
        {"period": "COMPARATIVE"},
    ):
        assert (await client.get(endpoint, headers=headers(), params=params)).status_code == 422
    generation = (await client.get(target, headers=headers())).json()["generation_id"]
    legacy, _ = await completed(app, client, version=5, generation=generation)
    assert (await client.get(legacy + "/rows", headers=headers())).status_code == 200
    assert (await client.get(legacy + "/hierarchy", headers=headers())).status_code == 409
    catalog = (
        await client.get(f"/v2/companies/{COMPANY}/report-definitions", headers=headers())
    ).json()["items"]
    trial = [item for item in catalog if item["definition"]["code"] == "TRIAL_BALANCE"]
    assert len(trial) == 1 and trial[0]["definition"]["version"] == 6


async def test_hierarchy_locators_two_tenants_and_immutable_frozen_ancestry(app, client):
    target, _ = await completed(app, client)
    other_tenant = uuid.uuid4()
    foreign, _ = await completed(app, client, tenant=other_tenant)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            nodes = list(await db.scalars(select(ReportHierarchyNode)))
            assert nodes and all(node.tenant_id == TENANT for node in nodes)
            assert all(str(node.job_id) == target.rsplit("/", 1)[1] for node in nodes)
        async with app.state.session_factory() as db, db.begin():
            node = await db.scalar(select(ReportHierarchyNode))
            node.parent_key = "root"
            node.depth += 1
            with pytest.raises(ConflictError, match="immutable"):
                await db.flush()
            await db.rollback()
    with tenant_scope(other_tenant):
        async with app.state.session_factory() as db:
            nodes = list(await db.scalars(select(ReportHierarchyNode)))
            assert nodes and all(str(node.job_id) == foreign.rsplit("/", 1)[1] for node in nodes)


async def test_more_than_200_siblings_page_once_with_full_totals_and_quiet_filter(app, client):
    from financial_fixture import financial_dataset
    from fixtures import source
    from sqlalchemy import event

    facts, ids = financial_dataset()
    cash = next(row.data for row in facts if str(row.source_id) == ids["cash"])
    for index in range(205):
        facts.append(
            source(
                "account",
                uuid.uuid4(),
                cash
                | {"code": f"QUIET{index:03}", "name": f"Quiet account {index}", "kind": "GENERAL"},
            )
        )
    job_reads = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT") and "report_job" in statement:
            job_reads.append(statement)

    event.listen(app.state.engine.sync_engine, "before_cursor_execute", record)
    try:
        target, _ = await completed(app, client, dataset=(facts, ids))
    finally:
        event.remove(app.state.engine.sync_engine, "before_cursor_execute", record)
    assert len(job_reads) < 80, "hierarchy publication must not query the job once per node"
    parent = "group:" + cash["group_id"]
    rows, cursor, total = [], None, None
    while True:
        result = await client.get(
            target + "/hierarchy",
            headers=headers(),
            params={"parent": parent, "limit": 50, **({"cursor": cursor} if cursor else {})},
        )
        assert result.status_code == 200, result.text
        page = result.json()
        total = total or page["summary"]
        assert page["summary"] == total and len(page["items"]) <= 50
        rows.extend(page["items"])
        cursor = page["page"]["next_cursor"]
        if cursor is None:
            break
    assert len(rows) == 206 and len({row["ordinal"] for row in rows}) == 206
    hidden = await client.get(
        target + "/hierarchy", headers=headers(), params={"parent": parent, "show_zero": False}
    )
    assert len(hidden.json()["items"]) == 1 and hidden.json()["summary"] == total


async def test_zero_filter_uses_all_six_amounts_in_each_frozen_period(app, client):
    from trial_balance_filter_fixture import filtering_dataset

    facts, ids = filtering_dataset()
    target, _ = await completed(
        app,
        client,
        dataset=(facts, ids),
        parameters={
            "comparative_from": "2027-04-01",
            "comparative_to": "2027-04-30",
        },
    )
    cash = next(row.data for row in facts if str(row.source_id) == ids["cash"])
    endpoint = target + "/hierarchy"
    parent = "group:" + cash["group_id"]
    current = await client.get(endpoint, headers=headers(), params={"parent": parent})
    assert current.status_code == 200, current.text
    assert len(current.json()["items"]) == 3
    totals = current.json()["summary"]
    assert totals["account_count"] == 7
    assert totals["period_debit"] == totals["period_credit"] == "367.0000"
    assert totals["closing_debit"] == totals["closing_credit"] == "300.0000"
    rows, cursor = [], None
    while True:
        response = await client.get(
            endpoint,
            headers=headers(),
            params={
                "parent": parent,
                "show_zero": False,
                "limit": 1,
                **({"cursor": cursor} if cursor else {}),
            },
        )
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["summary"] == totals
        rows.extend(page["items"])
        cursor = page["page"]["next_cursor"]
        if not cursor:
            break
    assert {row["data"]["node_key"] for row in rows} == {
        "account:" + ids["cash"],
        "account:" + ids["clearing"],
    }
    clearing = next(row["data"] for row in rows if row["data"]["name"] == "clearing")
    assert clearing["closing_debit"] == clearing["closing_credit"] == "0.0000"
    assert clearing["period_debit"] == clearing["period_credit"] == "7.0000"
    quiet = await client.get(
        endpoint,
        headers=headers(),
        params={
            "parent": "group:" + ids["quiet_group"],
            "show_zero": False,
        },
    )
    assert quiet.status_code == 200 and quiet.json()["items"] == []
    assert quiet.json()["summary"] == totals
    comparative = await client.get(
        endpoint,
        headers=headers(),
        params={
            "parent": parent,
            "period": "COMPARATIVE",
            "show_zero": False,
        },
    )
    assert comparative.status_code == 200, comparative.text
    assert [row["data"]["node_key"] for row in comparative.json()["items"]] == [
        "account:" + ids["cash"],
    ]
    # The fixture has no fiscal closing journal: all posted GL balances carry.
    comparative_totals = comparative.json()["summary"]
    assert comparative_totals["opening_debit"] == comparative_totals["opening_credit"] == "300.0000"
    assert comparative_totals["period_debit"] == comparative_totals["period_credit"] == "30.0000"
    assert comparative_totals["closing_debit"] == comparative_totals["closing_credit"] == "300.0000"
    assert comparative.json()["items"][0]["data"]["closing_debit"] == "210.0000"
    assert all(row["data"]["period"] == "COMPARATIVE" for row in comparative.json()["items"])
