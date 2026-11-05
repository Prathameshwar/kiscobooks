import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from test_framework_execution import proof
from test_native_ledger import prepared

from reports.domain.reporting.drilldowns import account_entries
from reports.models.framework import ReportJob
from reports.tasks.framework_worker import process


@pytest.mark.parametrize(
    "grain,date,end", [("DAY", "2026-04-15", "2026-04-15"), ("MONTH", "2026-04-01", "2026-04-20")]
)
def test_drilldown_uses_registered_bucket_and_comparative_dates(grain, date, end):
    account = str(uuid.uuid4())
    parameters = {
        "date_from": "2027-04-01",
        "date_to": "2027-04-20",
        "comparative_from": "2026-04-01",
        "comparative_to": "2026-04-20",
    }
    result = account_entries(
        parameters, {"account_id": account, "period": "COMPARATIVE", "grain": grain, "date": date}
    )
    assert result == {"account_id": account, "date_from": date, "date_to": end}
    assert account_entries(parameters, {"row_kind": "TOTAL"}) is None


async def test_drilldown_is_signed_idempotent_retains_source_display_and_current_authority(
    app, client, monkeypatch
):
    identities, _, ids = await prepared(app)
    app.state.settings.framework_enabled = app.state.settings.native_queries_enabled = True
    path = f"/v2/companies/{COMPANY}/report-runs"
    created = await client.post(
        path,
        headers=headers(),
        json={
            "code": "TRIAL_BALANCE",
            "generation_id": str(identities[2]),
            "parameters": {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "comparative_from": "2027-04-01",
                "comparative_to": "2027-04-30",
            },
        },
    )
    assert created.status_code == 202, created.text

    async def authority(job):
        return proof(job)

    parent_id = uuid.UUID(created.json()["id"])
    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, parent_id, authority
    )
    parent = path + "/" + str(parent_id)
    response = await client.get(parent + "/rows", headers=headers())
    assert response.status_code == 200, response.text
    rows = response.json()["items"]
    controls = [row for row in rows if row["data"]["row_kind"] == "TRIAL_BALANCE_CONTROL"]
    assert controls and all(
        [link["key"] for link in row["drilldowns"]] == ["row_detail"] for row in controls
    )
    account = next(
        row
        for row in rows
        if row["data"].get("account_id") == str(ids["cash"])
        and row["data"]["period"] == "COMPARATIVE"
    )
    token = next(
        link["token"] for link in account["drilldowns"] if link["key"] == "account_entries"
    )
    key = headers()
    for _ in range(2):
        result = await client.post(parent + "/drilldowns", headers=key, json={"token": token})
        assert result.status_code == 202, result.text
        child = result.json()
    assert child["generation_id"] == str(identities[2])
    assert child["origin"]["parent_id"] == str(parent_id)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            record = await db.get(ReportJob, uuid.UUID(child["id"]))
            original = await db.get(ReportJob, parent_id)
            assert record.display == original.display
            assert record.parameters["date_from"] == "2027-04-01"
            assert record.parameters["account_id"] == str(ids["cash"])
        async with app.state.session_factory() as db, db.begin():
            record = await db.get(ReportJob, uuid.UUID(child["id"]))
            record.origin = None
            with pytest.raises(ConflictError, match="immutable"):
                await db.flush()
            await db.rollback()
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(child["id"]),
        authority,
    )
    assert (await client.get(path + "/" + child["id"], headers=headers())).json()[
        "status"
    ] == "COMPLETE"
    assert (
        await client.post(parent + "/drilldowns", headers=headers(), json={"token": token + "x"})
    ).status_code == 422
    for denied in (headers(user=uuid.uuid4()), headers(permissions=PERMISSIONS - {"ledger.read"})):
        assert (
            await client.post(parent + "/drilldowns", headers=denied, json={"token": token})
        ).status_code == 403
    assert (await client.post(parent + "/drilldowns", json={"token": token})).status_code == 401

    from reports.domain.reporting.registry import Registry

    original = Registry.resolve

    def removed_target(registry, code, version=None):
        if code == "ACCOUNT_LEDGER":
            raise KeyError(code)
        return original(registry, code, version)

    monkeypatch.setattr(Registry, "resolve", removed_target)
    retained = await client.get(parent + "/rows", headers=headers())
    assert retained.status_code == 200, retained.text
    assert [row["data"] for row in retained.json()["items"]] == [row["data"] for row in rows]
    assert all(
        all(link["key"] == "row_detail" for link in row["drilldowns"])
        for row in retained.json()["items"]
    )
