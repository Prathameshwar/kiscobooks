"""Committed owner generations order stock even when different writers' clocks differ."""

from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from voucher_execution import EffectReference, ExecutionResult

from accounting.models.voucher_execution import VoucherExecution, VoucherSourceGuard
from accounting.tasks.stock_reconciliation import assert_physical
from accounting.tasks.stock_reversal import guard
from tests.conftest import COMPANY, TENANT
from tests.test_stock_ledger import item, ledger, line, prepare_serial, values, warehouse


async def certify(db, posting, generation):
    identity, source_id = uuid7(), uuid7()
    db.add(
        VoucherSourceGuard(
            **(values() | {"id": source_id}),
            voucher_id=posting.voucher_id,
            committed_execution_id=posting.execution_id,
        )
    )
    await db.flush()
    result = ExecutionResult(
        protocol_version=2,
        tenant_id=TENANT,
        company_id=COMPANY,
        operation_id=posting.operation_id,
        execution_id=posting.execution_id,
        content_hash=posting.content_hash,
        configuration_hash="a" * 64,
        request_hash="a" * 64,
        outcome="COMMITTED",
        committed_at=utcnow(),
        committed_generation=generation,
        effects=(
            EffectReference(owner="accounting", effect_kind="STOCK", effect_id=posting.id),
            EffectReference(owner="accounting", effect_kind="SOURCE_RECEIPT", effect_id=identity),
        ),
    )
    db.add(
        VoucherExecution(
            **(values() | {"id": identity}),
            source_guard_id=source_id,
            execution_id=posting.execution_id,
            operation_id=posting.operation_id,
            request_hash=result.request_hash,
            command={
                "voucher_id": str(posting.voucher_id),
                "revision_id": str(posting.revision_id),
            },
            result=result.model_dump(mode="json"),
        )
    )
    await db.flush()


def skew(monkeypatch):
    import uuid

    from accounting.tasks import stock_ledger
    from tests import test_stock_ledger

    def earlier_clock():
        return uuid.UUID(int=uuid7().int - (600_000 << 80))

    monkeypatch.setattr(stock_ledger, "uuid7", earlier_clock)
    monkeypatch.setattr(test_stock_ledger, "uuid7", earlier_clock)


async def test_reversal_refuses_later_committed_pool_effect_with_lower_uuid(app, monkeypatch):
    product, location = item(), warehouse()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            original = owner.posting
            await owner.receive(line(product, location, 2), product, location, value=Decimal("10"))
            await certify(db, original, 10)
        with monkeypatch.context() as changed:
            skew(changed)
            async with app.state.session_factory.begin() as db:
                owner = await ledger(db, "DISPATCH")
                assert owner.posting.id.int < original.id.int
                await owner.issue(line(product, location, 1), product, location)
                await certify(db, owner.posting, 20)
        with pytest.raises(ConflictError, match="later dependent"):
            async with app.state.session_factory.begin() as db:
                reversing = await ledger(db, "REVERSAL", reverses_id=original.id)
                await guard(reversing, original)


async def test_latest_serial_custody_uses_commit_generation_across_writer_clock_skew(
    app, monkeypatch
):
    product, location, unit = (
        item().model_copy(update={"serial_tracking": True}),
        warehouse(),
        uuid7(),
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            await prepare_serial(db, product, unit)
            owner = await ledger(db)
            await owner.receive(
                line(product, location, 1, unit_ids=(unit,)), product, location, value=Decimal("10")
            )
            await certify(db, owner.posting, 10)
        with monkeypatch.context() as changed:
            skew(changed)
            async with app.state.session_factory.begin() as db:
                owner = await ledger(db, "DISPATCH")
                await owner.issue(line(product, location, 1, unit_ids=(unit,)), product, location)
                await certify(db, owner.posting, 20)
        async with app.state.session_factory.begin() as db:
            await assert_physical(db, COMPANY)


@pytest.mark.parametrize("strategy", ["FIFO", "FEFO"])
async def test_same_day_fifo_cost_and_physical_age_follow_commit_order(app, monkeypatch, strategy):
    product = item().model_copy(update={"issue_strategy": strategy})
    location = warehouse()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            first = await owner.receive(
                line(product, location, 1), product, location, value=Decimal("10")
            )
            await certify(db, owner.posting, 10)
        with monkeypatch.context() as changed:
            skew(changed)
            async with app.state.session_factory.begin() as db:
                owner = await ledger(db)
                await owner.receive(
                    line(product, location, 1), product, location, value=Decimal("20")
                )
                await certify(db, owner.posting, 20)
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, "DISPATCH")
            issued = await owner.issue(line(product, location, 1), product, location)
            assert (issued.value, issued.origins[0].origin_id) == (
                Decimal("-10"),
                first.origins[0].origin_id,
            )
