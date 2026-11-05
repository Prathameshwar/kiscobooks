"""Native movement evidence commits with stock, GL and the common owner receipt."""

from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from reporting_contract.inventory import Movement
from sqlalchemy import func, select
from voucher_execution import ExecutionCommand
from voucher_execution.transport import command_digest

from accounting.models.inventory_reporting import InventoryReportRecord
from accounting.models.stock import StockPosting
from accounting.tasks import stock_reporting
from accounting.tasks.stock_execution import dispatch
from tests.conftest import SECRET, TENANT
from tests.test_ledger_api import journal_setup
from tests.test_stock_effects import Source, captured, configure, source
from tests.test_stock_ledger import item, warehouse


async def request_for(app, client):
    _, period, owner = await journal_setup(client, app)
    await configure(app)
    product, location = item(), warehouse()
    request = captured(period, product, location).model_copy(
        update={"voucher_number": "GRN/26/001"}
    )
    request = request.model_copy(update={"request_hash": command_digest(request)})
    return request, owner, Source(source(request, product, location))


async def test_native_movement_handoff_retains_number_order_and_exact_cost_on_replay(app, client):
    request, owner, facts = await request_for(app, client)
    for _ in range(2):
        result = await dispatch(
            app.state.session_factory,
            request,
            secret=SECRET.encode(),
            client=owner,
            source_client=facts,
            enabled=True,
        )
        assert result.outcome == "COMMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            records = list(await db.scalars(select(InventoryReportRecord)))
            assert len(records) == 1  # Never invent full-company coverage from one receipt.
            movement = Movement.model_validate(records[0].payload)
            assert movement.voucher_number == "GRN/26/001"
            assert movement.sequence == result.committed_generation * 1000 + 1
            assert Decimal(movement.quantity_delta) == Decimal("2")
            assert Decimal(movement.value_delta) == Decimal("12.50")
            assert movement.action == "RECEIPT"
            assert str(movement.line_id) == request.source_payload["stock"]["lines"][0]["line_id"]
        with pytest.raises(ConflictError, match="immutable"):
            async with app.state.session_factory.begin() as db:
                record = await db.get(InventoryReportRecord, movement.movement_id)
                changed = movement.model_copy(update={"voucher_number": "Different"})
                record.payload = changed.model_dump(mode="json")
                await db.flush()


async def test_failed_reporting_handoff_rolls_back_stock_and_owner_effects(
    app, client, monkeypatch
):
    request, owner, facts = await request_for(app, client)

    async def fail(*args, **kwargs):
        raise ConflictError("reporting handoff unavailable")

    monkeypatch.setattr(stock_reporting, "publish", fail)
    result = await dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=facts,
        enabled=True,
    )
    assert result.outcome == "REJECTED" and result.rejection_code == "CONTENT_REJECTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            assert 0 == await db.scalar(select(func.count(StockPosting.id)))
            assert 0 == await db.scalar(select(func.count(InventoryReportRecord.id)))


async def test_legacy_accepted_commands_keep_their_original_wire_and_request_digest(app, client):
    _, period, _ = await journal_setup(client, app)
    original = captured(period, item(), warehouse())
    wire = original.model_dump(mode="json")
    assert "voucher_number" not in wire
    replay = ExecutionCommand.model_validate(wire)
    assert replay.model_dump(mode="json") == wire
    assert command_digest(replay) == original.request_hash
