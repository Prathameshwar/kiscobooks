"""Reconciliation reads the exact immutable proof behind a published source generation."""

import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT, headers
from financial_fixture import financial_manifest
from test_framework_execution import proof
from test_native_ledger import prepared

from reports.queries.native_reconciliation import execute
from reports.tasks.framework_worker import process
from reports.tasks.report_catalog import catalog


async def test_verified_reconciliation_parity_bounds_and_scope(app):
    identities, facts, _ = await prepared(app)
    expected = (
        catalog()
        .resolve("SOURCE_RECONCILIATION")
        .handler.execute(facts, identities[2], {}, financial_manifest(facts).control)
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await execute(db, COMPANY, identities[2], 100000) == expected
            with pytest.raises(ConflictError, match="bound"):
                await execute(db, COMPANY, identities[2], 1)
            with pytest.raises(ConflictError, match="verified"):
                await execute(db, uuid.uuid4(), identities[2], 100000)
    with tenant_scope(uuid.uuid4()):
        async with app.state.session_factory() as db:
            with pytest.raises(ConflictError, match="verified"):
                await execute(db, COMPANY, identities[2], 100000)


async def test_native_reconciliation_v2_avoids_reference_fact_limit(app, client):
    identities, facts, _ = await prepared(app)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    app.state.settings.reference_fact_limit = 1
    path = f"/v2/companies/{COMPANY}/report-runs"
    response = await client.post(
        path,
        headers=headers(),
        json={
            "code": "SOURCE_RECONCILIATION",
            "generation_id": str(identities[2]),
            "parameters": {},
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
    expected, evidence = (
        catalog()
        .resolve("SOURCE_RECONCILIATION")
        .handler.execute(facts, identities[2], {}, financial_manifest(facts).control)
    )
    assert [row["data"] for row in values.json()["items"]] == expected
    assert result.json()["result"]["evidence"] == evidence
