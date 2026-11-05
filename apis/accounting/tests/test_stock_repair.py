"""Offline recovery preserves immutable evidence and activates only reconciled state."""

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import func, select

from accounting.models import stock as s
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.tasks import stock_repair as repair
from accounting.tasks.stock_claims import customer_return
from accounting.tasks.stock_reconciliation import assert_physical
from tests.conftest import COMPANY, TENANT
from tests.test_stock_ledger import item, ledger, line, prepare_serial, warehouse
from tests.test_stock_ordering import certify


async def settle(db, owner, generation):
    intent = await db.get(VoucherMoneyIntent, owner.posting.intent_id)
    intent.status = "COMMITTED"
    await certify(db, owner.posting, generation)


@pytest.mark.parametrize("method", ["FIFO", "MOVING_AVERAGE"])
async def test_recovery_reconstructs_quantities_costs_origins_units_and_claims(app, method):
    product = item(method).model_copy(update={"serial_tracking": True})
    location = warehouse()
    units = tuple(uuid7() for _ in range(3))
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            for unit in units:
                await prepare_serial(db, product, unit)
            owner = await ledger(db)
            await owner.receive(
                line(product, location, 3, unit_ids=units), product, location, value=Decimal("10")
            )
            await settle(db, owner, 10)
            owner = await ledger(db, "DISPATCH")
            issued = await owner.issue(
                line(product, location, 2, unit_ids=units[:2]), product, location
            )
            await settle(db, owner, 20)
            owner = await ledger(db, "CUSTOMER_RETURN")
            await customer_return(
                owner,
                line(
                    product,
                    location,
                    1,
                    unit_ids=(units[0],),
                    source_movement_id=issued.movement_id,
                ),
                product,
                location,
            )
            await settle(db, owner, 30)
            await assert_physical(db, COMPANY)
            assert not (await repair.preview(db, TENANT, COMPANY)).changes
        async with app.state.session_factory.begin() as db:
            for model, field in (
                (s.StockBalance, "quantity"),
                (s.StockCostPool, "value"),
                (s.StockOriginBalance, "quantity"),
                (s.StockSourceClaim, "value"),
                (s.StockOriginClaim, "quantity"),
            ):
                row = await db.scalar(select(model).limit(1))
                setattr(row, field, getattr(row, field) + Decimal("0.0001"))
                if model == s.StockCostPool:
                    row.method = "MOVING_AVERAGE" if method == "FIFO" else "FIFO"
            if method == "FIFO":
                layer = await db.scalar(
                    select(s.StockCostLayer).where(s.StockCostLayer.remaining_quantity > 0).limit(1)
                )
                layer.remaining_value -= Decimal("0.0001")
            state = await db.scalar(
                select(s.StockUnitPosition).where(s.StockUnitPosition.unit_id == units[0])
            )
            state.last_movement_id = issued.movement_id
        async with app.state.session_factory.begin() as db:
            history_count = await db.scalar(select(func.count(s.StockMovement.id)))
            plan = await repair.preview(db, TENANT, COMPANY)
            expected_generation, digest = plan.setup.generation, plan.digest
            assert len(plan.changes) == (7 if method == "FIFO" else 6)
            assert not db.dirty and not db.new
        with pytest.raises(ConflictError, match="fresh preview"):
            async with app.state.session_factory.begin() as db:
                await repair.apply(
                    db,
                    TENANT,
                    COMPANY,
                    expected_generation=expected_generation,
                    expected_digest="0" * 64,
                    reason="Reviewed recovery",
                )
        async with app.state.session_factory.begin() as db:
            fixed = await repair.apply(
                db,
                TENANT,
                COMPANY,
                expected_generation=expected_generation,
                expected_digest=digest,
                reason="Reviewed recovery",
            )
            assert fixed.setup.generation == expected_generation + 1
        async with app.state.session_factory.begin() as db:
            await assert_physical(db, COMPANY)
            assert (await db.scalar(select(s.StockCostPool))).method == method
            assert not (await repair.preview(db, TENANT, COMPANY)).changes
            assert history_count == await db.scalar(select(func.count(s.StockMovement.id)))
            assert 1 == await db.scalar(
                select(func.count())
                .select_from(Outbox)
                .where(Outbox.event_type == "accounting.stock_projection.rebuild")
            )
            audit = await db.scalar(
                select(Outbox).where(Outbox.event_type == "accounting.stock_projection.rebuild")
            )
            assert audit.payload["context"] == {
                "projection_digest": digest,
                "repaired_rows": len(fixed.changes),
                "generation": expected_generation + 1,
            }
            assert not {"projection_digest", "repaired_rows", "generation"} & audit.payload.keys()
            # Cross-owner wire probe: load only Audit's pure payload validator in
            # a separate interpreter; no production dependency or foreign ORM.
            subprocess.run(  # noqa: S603 -- Fixed interpreter/code and repository path; payload uses stdin, never a shell.
                [
                    sys.executable,
                    "-c",
                    "import json,sys; sys.path.insert(0,sys.argv[1]); "
                    "from audit.domain.ingest import AuditEventPayload; "
                    "AuditEventPayload.model_validate(json.load(sys.stdin))",
                    str(Path(__file__).resolve().parents[2] / "audit/src"),
                ],
                input=json.dumps(audit.payload),
                text=True,
                capture_output=True,
                check=True,
                timeout=15,
            )
        with pytest.raises(ConflictError, match="fresh preview"):
            async with app.state.session_factory.begin() as db:
                await repair.apply(
                    db,
                    TENANT,
                    COMPANY,
                    expected_generation=expected_generation,
                    expected_digest=digest,
                    reason="Reviewed recovery",
                )


async def test_recovery_denies_wrong_scope_and_prepared_execution(app):
    product, location = item(), warehouse()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(line(product, location, 1), product, location, value=Decimal("10"))
        async with app.state.session_factory.begin() as db:
            with pytest.raises(ConflictError, match="prepared executions"):
                await repair.preview(db, TENANT, COMPANY)
            with pytest.raises(ConflictError, match="initialized company"):
                await repair.preview(db, uuid7(), COMPANY)
            with pytest.raises(ConflictError, match="initialized company"):
                await repair.preview(db, TENANT, uuid7())
    with tenant_scope(uuid7()):
        async with app.state.session_factory.begin() as db:
            with pytest.raises(ConflictError, match="initialized company"):
                await repair.preview(db, TENANT, COMPANY)


async def test_failed_reconciliation_rolls_back_repair_and_its_audit(app, monkeypatch):
    product, location = item(), warehouse()
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(line(product, location, 2), product, location, value=Decimal("10"))
            await settle(db, owner, 10)
        async with app.state.session_factory.begin() as db:
            balance = await db.scalar(select(s.StockBalance))
            balance.quantity = Decimal("3")
        async with app.state.session_factory.begin() as db:
            plan = await repair.preview(db, TENANT, COMPANY)
            generation, digest = plan.setup.generation, plan.digest

        async def failed_control(db, company):
            raise ConflictError("inventory GL does not reconcile")

        with monkeypatch.context() as changed:
            changed.setattr(repair, "assert_value_control", failed_control)
            with pytest.raises(ConflictError, match="inventory GL"):
                async with app.state.session_factory.begin() as db:
                    await repair.apply(
                        db,
                        TENANT,
                        COMPANY,
                        expected_generation=generation,
                        expected_digest=digest,
                        reason="Reviewed recovery",
                    )
        async with app.state.session_factory.begin() as db:
            assert (await db.scalar(select(s.StockBalance))).quantity == Decimal("3")
            assert (await repair.preview(db, TENANT, COMPANY)).digest == digest
            assert 0 == await db.scalar(
                select(func.count())
                .select_from(Outbox)
                .where(Outbox.event_type == "accounting.stock_projection.rebuild")
            )


async def test_recovery_refuses_missing_native_origin_history_before_proposing_changes(
    app, client, engine
):
    from sqlalchemy import delete

    from accounting.tasks.stock_execution import dispatch
    from tests.conftest import SECRET
    from tests.test_ledger_api import journal_setup
    from tests.test_stock_effects import Source, captured, configure, source

    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    request = captured(period, product, location, amount="0.00")
    result = await dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(source(request, product, location)),
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
    # Simulate storage loss through the disposable schema connection. Application
    # ORM paths correctly forbid deleting this immutable history.
    table = s.StockOriginAllocation.__table__
    async with engine.begin() as connection:
        await connection.execute(
            delete(table).where(table.c.tenant_id == TENANT, table.c.company_id == COMPANY)
        )
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            with pytest.raises(ConflictError, match="immutable stock history"):
                await repair.preview(db, TENANT, COMPANY)
