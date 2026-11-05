"""Dispatch/receive transfer legs with one reserved transit shipment claim."""

from billing_platform.errors import ConflictError
from sqlalchemy import select
from voucher_execution.stock import StockLine
from voucher_execution.stock_facts import StockItemFact, StockWarehouseFact

from accounting.models.stock import StockPosition, StockTransferDestination
from accounting.tasks.stock_claims import SourceClaim, claim, consume
from accounting.tasks.stock_ledger import Leg, StockLedger


def transit_item(item: StockItemFact) -> StockItemFact:
    # Transit escrow retains each shipment's original value; it never blends the
    # costing of unrelated shipments. Actual warehouses retain the SKU method.
    return item.model_copy(update={"valuation_method": "FIFO"})


async def dispatch(
    ledger: StockLedger,
    line: StockLine,
    item: StockItemFact,
    source: StockWarehouseFact,
    transit: StockWarehouseFact,
    destination: StockWarehouseFact,
) -> tuple[Leg, Leg]:
    if transit.kind != "INTERNAL_TRANSIT" or source.kind == "INTERNAL_TRANSIT":
        raise ConflictError("a transfer dispatch requires its reserved company transit warehouse")
    issued = await ledger.issue(line, item, source)
    inward_line = line.model_copy(
        update={
            "warehouse_id": transit.warehouse_id,
            "bin_id": None,
            "destination_warehouse_id": None,
            "destination_bin_id": None,
        }
    )
    received = await ledger.receive(
        inward_line,
        transit_item(item),
        transit,
        value=-issued.value,
        origins=issued.origins,
        unit_values=issued.units,
        source_movement_id=issued.movement_id,
    )
    target_line = line.model_copy(
        update={"warehouse_id": destination.warehouse_id, "bin_id": line.destination_bin_id}
    )
    target, _ = await ledger.position(target_line, destination)
    ledger.add(
        StockTransferDestination,
        transit_movement_id=received.movement_id,
        destination_position_id=target.id,
    )
    await ledger.db.flush()
    return issued, received


async def receive(
    ledger: StockLedger,
    line: StockLine,
    item: StockItemFact,
    destination: StockWarehouseFact,
    transit: StockWarehouseFact,
) -> tuple[Leg, Leg, SourceClaim]:
    if transit.kind != "INTERNAL_TRANSIT" or destination.kind == "INTERNAL_TRANSIT":
        raise ConflictError(
            "a transfer receipt requires an actual destination and reserved transit"
        )
    source = await claim(
        ledger,
        line,
        claim_type="TRANSFER",
        source_action="TRANSFER_DISPATCH",
        source_leg="IN",
    )
    manifest = await ledger.db.scalar(
        select(StockTransferDestination).where(
            StockTransferDestination.company_id == ledger.posting.company_id,
            StockTransferDestination.transit_movement_id == source.source.id,
        )
    )
    if manifest is None:
        raise ConflictError("the original shipment has no retained destination")
    target = await ledger.scoped(StockPosition, manifest.destination_position_id)
    if (target.warehouse_id, target.bin_id) != (line.warehouse_id, line.bin_id):
        raise ConflictError("receipt destination differs from the original transfer dispatch")
    position = await ledger.scoped(StockPosition, source.source.position_id)
    if position.warehouse_id != transit.warehouse_id or position.custody_kind != "TRANSIT":
        raise ConflictError("the original shipment is not held in this company's reserved transit")
    outward_line = line.model_copy(update={"warehouse_id": transit.warehouse_id, "bin_id": None})
    issued = await ledger.issue(
        outward_line,
        transit_item(item),
        transit,
        origins=source.origins,
        source_movement_id=source.source.id,
        transit_source_id=source.source.id,
        transit_value=source.value,
        transit_units=source.units if item.serial_tracking else None,
    )
    received = await ledger.receive(
        line,
        item,
        destination,
        value=source.value,
        origins=issued.origins,
        unit_values=issued.units,
        source_movement_id=source.source.id,
    )
    consume(ledger, source, line.quantity, received.movement_id)
    await ledger.db.flush()
    return issued, received, source
