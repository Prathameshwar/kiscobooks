"""Opening adoption obeys the same period authority as other cutover transitions."""

import datetime as dt

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from sqlalchemy import func, select

from accounting.models.fiscal import FiscalPeriod
from accounting.models.ledger import Journal
from accounting.models.stock import StockPosting
from accounting.models.stock_opening import StockOpeningControl, StockOpeningRevision
from accounting.models.stock_tracking import StockLot
from accounting.tasks import stock_opening_control
from accounting.tasks.stock_execution import _dispatch
from tests.conftest import COMPANY, SECRET, TENANT
from tests.test_ledger_api import LEDGER_PERMISSIONS, journal_setup, ledger_headers
from tests.test_stock_effects import Source, captured, configure, source
from tests.test_stock_ledger import item, warehouse
from tests.test_stock_opening_api import BASE, auth, manifest
from tests.test_stock_opening_cohorts import opening_fixture, settle_posting_delivery


async def legacy_history(client, app, monkeypatch):
    _, period, owner = await journal_setup(client, app)
    await configure(app, finalize_zero=False)
    product, location = item(), warehouse()
    request = captured(period, product, location)

    async def previous_release_gate(db, company, body):
        return None

    # The previous release had no opening control. Seed genuine native effects
    # with only that new gate omitted, then restore it before testing adoption.
    with monkeypatch.context() as previous:
        previous.setattr(stock_opening_control, "require_posting", previous_release_gate)
        result, _ = await _dispatch(
            app.state.session_factory,
            request,
            secret=SECRET.encode(),
            client=owner,
            source_client=Source(source(request, product, location)),
            enabled=True,
        )
    assert result.outcome == "COMMITTED"
    await settle_posting_delivery(app, owner)


@pytest.mark.parametrize(
    ("status", "day"),
    [
        ("CLOSED", dt.date(2026, 4, 1)),
        ("LOCKED", dt.date(2026, 4, 1)),
        ("CLOSED", dt.date(2026, 5, 1)),
    ],
)
async def test_legacy_adoption_respects_closed_and_later_books(
    client, app, monkeypatch, status, day
):
    await legacy_history(client, app, monkeypatch)
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            period = await db.scalar(
                select(FiscalPeriod).where(
                    FiscalPeriod.company_id == COMPANY,
                    FiscalPeriod.start_date <= day,
                    FiscalPeriod.end_date >= day,
                )
            )
            assert period is not None
            period.status = status
        # Period changes enqueue their own audit at commit. Snapshot afterward
        # so the assertion below isolates the rejected adoption request.
        async with app.state.session_factory() as db:
            counts = {
                model: await db.scalar(select(func.count(model.id)))
                for model in (StockPosting, Journal, Outbox)
            }
    response = await client.post(
        BASE + "/adopt",
        headers=auth(),
        json=manifest() | {"adopt_existing": True},
    )
    assert response.status_code == 409, response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockOpeningControl.id))) == 0
            assert await db.scalar(select(func.count(StockOpeningRevision.id))) == 0
            for model, count in counts.items():
                assert await db.scalar(select(func.count(model.id))) == count


async def test_legacy_adoption_requires_period_post_authority(client, app, monkeypatch):
    await legacy_history(client, app, monkeypatch)
    permitted = (LEDGER_PERMISSIONS | {"accounting.stock.read", "accounting.stock.configure"}) - {
        "period.post"
    }
    response = await client.post(
        BASE + "/adopt",
        headers=ledger_headers(permissions=permitted, features={"inventory"}),
        json=manifest() | {"adopt_existing": True},
    )
    assert response.status_code == 403, response.text


@pytest.mark.parametrize("expiry", [dt.date(2026, 4, 1), dt.date(2026, 4, 11)])
async def test_native_opening_records_unexpired_stock_below_issue_remaining_life(
    client, app, expiry
):
    request, product, location, _, owner = await opening_fixture(client, app, tracking="BATCH")
    product = product.model_copy(update={"minimum_remaining_life_days": 30})
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            lot = await db.scalar(select(StockLot).where(StockLot.item_id == product.item_id))
            assert lot is not None
            lot.expires_on = expiry
    result, _ = await _dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(source(request, product, location)),
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
