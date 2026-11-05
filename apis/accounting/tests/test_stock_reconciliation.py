"""Projection expectations are rebuilt from actual immutable movement/value evidence."""

import datetime as dt
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from sqlalchemy import select

from accounting.models.stock import StockBalance, StockCostPool, StockOriginBalance
from accounting.tasks.stock_reconciliation import (
    assert_physical,
    assert_value_control,
    closing_checks,
)
from tests.conftest import COMPANY, SECRET, TENANT
from tests.test_ledger_api import journal_setup
from tests.test_stock_effects import Source, captured, configure, source
from tests.test_stock_ledger import item, ledger, line, warehouse


@pytest.mark.parametrize("method", ["FIFO", "MOVING_AVERAGE"])
async def test_rebuild_expectations_detect_projection_drift_without_writing_history(app, method):
    product, location = item(method), warehouse()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(line(product, location, 3), product, location, value=Decimal("10"))
            owner = await ledger(db, "DISPATCH")
            await owner.issue(line(product, location, 1), product, location)
            await assert_physical(db, COMPANY)
        for model, field in (
            (StockBalance, "quantity"),
            (StockCostPool, "value"),
            (StockOriginBalance, "quantity"),
        ):
            with pytest.raises(ConflictError, match="reconcile"):
                async with app.state.session_factory.begin() as db:
                    row = await db.scalar(select(model))
                    setattr(row, field, getattr(row, field) + Decimal("1"))
                    await db.flush()
                    await assert_physical(db, COMPANY)
            async with app.state.session_factory.begin() as db:
                await assert_physical(db, COMPANY)


async def test_native_valued_execution_reconciles_stock_and_gl_control(app, client):
    from accounting.tasks.stock_execution import dispatch

    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    request = captured(period, product, location)
    result = await dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(source(request, product, location)),
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            await assert_physical(db, COMPANY)
            await assert_value_control(db, COMPANY)
        # A consistent quantity/cost history alone cannot conceal a missing GL effect.
        with pytest.raises(ConflictError, match="inventory GL"):
            async with app.state.session_factory.begin() as db:
                from accounting.models.stock import StockAccountPolicy

                policy = await db.scalar(select(StockAccountPolicy))
                extra = await ledger(db, account_policy_id=policy.id)
                await extra.receive(
                    line(product, location, 1), product, location, value=Decimal("1")
                )
                # This deliberately uncertified low-level effect must also fail
                # the separate GL control, without weakening receipt validation.
                await assert_value_control(db, COMPANY)
        async with app.state.session_factory.begin() as db:
            await assert_value_control(db, COMPANY)


@pytest.mark.parametrize("amount", ["0.00", "12.50"])
async def test_stock_confirmation_blocks_period_close_until_delivery(app, client, amount):
    from accounting.tasks.stock_execution import dispatch

    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    request = captured(period, product, location, amount=amount)
    result = await dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(source(request, product, location)),
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            with pytest.raises(ConflictError, match="confirmations"):
                await closing_checks(db, COMPANY, dt.date(2026, 4, 1), dt.date(2026, 4, 30))
            event = await db.scalar(
                select(Outbox).where(Outbox.event_type == "accounting.stock_posting.confirm")
            )
            assert event is not None
            event.published_at = utcnow()
            await db.flush()
            await closing_checks(db, COMPANY, dt.date(2026, 4, 1), dt.date(2026, 4, 30))


async def test_prepared_stock_execution_blocks_period_close(app, client):
    from accounting.api.auth import delegated_access
    from accounting.tasks.stock_execution import prepare

    _, period, _ = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    request = captured(period, product, location, amount="0.00")
    current = delegated_access(
        request.authority,
        SECRET.encode(),
        tenant_id=TENANT,
        company_id=COMPANY,
        actor_user_id=request.actor_user_id,
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            await prepare(db, current, request, source(request, product, location))
        async with app.state.session_factory.begin() as db:
            with pytest.raises(ConflictError, match="pending stock executions"):
                await closing_checks(db, COMPANY, dt.date(2026, 4, 1), dt.date(2026, 4, 30))
            await closing_checks(db, COMPANY, dt.date(2026, 3, 1), dt.date(2026, 3, 31))


async def test_serial_custody_checks_identity_even_when_position_counts_still_balance(app):
    from billing_platform.ids import uuid7

    from accounting.models.stock import StockUnitPosition
    from tests.test_stock_ledger import prepare_serial

    product = item().model_copy(update={"serial_tracking": True})
    first, second = warehouse(), warehouse()
    one, two = uuid7(), uuid7()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            await prepare_serial(db, product, one)
            await prepare_serial(db, product, two)
            owner = await ledger(db)
            await owner.receive(
                line(product, first, 1, unit_ids=(one,)), product, first, value=Decimal("10")
            )
            owner = await ledger(db)
            await owner.receive(
                line(product, second, 1, unit_ids=(two,)), product, second, value=Decimal("20")
            )
            await assert_physical(db, COMPANY)
        with pytest.raises(ConflictError, match="serial custody"):
            async with app.state.session_factory.begin() as db:
                states = list(await db.scalars(select(StockUnitPosition)))
                states[0].position_id, states[1].position_id = (
                    states[1].position_id,
                    states[0].position_id,
                )
                await db.flush()
                await assert_physical(db, COMPANY)


async def test_partial_claim_and_reversal_counters_reconcile_to_immutable_allocations(app):
    from accounting.models.stock import StockOriginClaim, StockPosting, StockSourceClaim
    from accounting.tasks.stock_claims import customer_return
    from accounting.tasks.stock_reversal import guard, reverse_leg

    product, location = item(), warehouse()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(line(product, location, 3), product, location, value=Decimal("10"))
            owner = await ledger(db, "DISPATCH")
            issued = await owner.issue(line(product, location, 2), product, location)
            owner = await ledger(db, "CUSTOMER_RETURN")
            original = owner.posting.id
            await customer_return(
                owner,
                line(product, location, 1, source_movement_id=issued.movement_id),
                product,
                location,
            )
            await assert_physical(db, COMPANY)
        for model, field in (
            (StockSourceClaim, "quantity"),
            (StockSourceClaim, "value"),
            (StockOriginClaim, "quantity"),
        ):
            with pytest.raises(ConflictError, match="source claims"):
                async with app.state.session_factory.begin() as db:
                    row = await db.scalar(select(model))
                    setattr(row, field, getattr(row, field) + Decimal("0.0001"))
                    await db.flush()
                    await assert_physical(db, COMPANY)
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, "REVERSAL", reverses_id=original)
            for movement in await guard(owner, await db.get(StockPosting, original)):
                await reverse_leg(owner, movement, product, location)
            await assert_physical(db, COMPANY)
            counters = list(await db.scalars(select(StockSourceClaim)))
            assert any(row.claim_type == "RETURN" and row.quantity == 0 for row in counters)
            assert any(row.claim_type == "REVERSAL" and row.quantity == 1 for row in counters)
