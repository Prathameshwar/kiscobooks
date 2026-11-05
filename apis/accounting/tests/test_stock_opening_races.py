"""Real native writers serialize opening claims and the finalization fence."""

import asyncio

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from voucher_execution.transport import command_digest

from accounting.models.stock import StockCostPool, StockPosting
from accounting.models.stock_opening import StockOpeningClaim, StockOpeningControl
from accounting.tasks.stock_execution import dispatch
from tests.conftest import SECRET, TENANT
from tests.test_ledger_api import journal_setup
from tests.test_stock_effects import Source, configure, source
from tests.test_stock_opening_api import BASE, auth, manifest
from tests.test_stock_opening_cohorts import opening_fixture

pytestmark = pytest.mark.mysql


async def test_competing_finalizers_commit_one_reviewed_transition(client, app, engine):
    if engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("requires real native row locks")
    await journal_setup(client, app)
    await configure(app, finalize_zero=False)
    created = await client.post(BASE, json=manifest(), headers=auth())
    assert created.status_code == 201, created.text
    row = created.json()
    body = {
        "expected_version": row["expected_version"],
        "manifest_hash": row["manifest_hash"],
        "reason": "Reviewed concurrent zero-stock finalization",
    }
    results = await asyncio.gather(
        *(client.post(BASE + f"/{row['id']}/finalize", json=body, headers=auth()) for _ in range(2))
    )
    assert sorted(result.status_code for result in results) == [200, 409]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            control = await db.scalar(select(StockOpeningControl))
            assert control.status == "FINALIZED" and control.row_version == 2


async def test_competing_openings_cannot_post_one_cohort_twice(client, app, engine):
    if engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("requires real native row locks")
    request, product, location, _, owner = await opening_fixture(client, app)
    duplicate = request.model_copy(
        update={
            "voucher_id": uuid7(),
            "revision_id": uuid7(),
            "operation_id": uuid7(),
            "execution_id": uuid7(),
        }
    )
    duplicate = duplicate.model_copy(update={"request_hash": command_digest(duplicate)})

    async def post(command):
        return await dispatch(
            app.state.session_factory,
            command,
            secret=SECRET.encode(),
            client=owner,
            source_client=Source(source(command, product, location)),
            enabled=True,
        )

    async with asyncio.timeout(30):
        results = await asyncio.gather(post(request), post(duplicate))
    assert sorted(result.outcome for result in results) == ["COMMITTED", "REJECTED"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockPosting.id))) == 1
            assert await db.scalar(select(func.count(StockOpeningClaim.id))) == 2
            pool = await db.scalar(select(StockCostPool))
            assert pool.quantity == 5 and pool.value == 80
