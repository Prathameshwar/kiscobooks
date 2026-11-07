"""Commit-bound native stock movement handoff to the existing Reporting feed.

It retains the real issued voucher number and serialized owner order. It never
asserts full-company report coverage, invents Catalog labels, treats historical
bin deltas as residual assets, or enables Reports before a complete source cut.
Legacy accepted commands without a number remain replayable; their reporting
backfill requires verified owner metadata, never a UUID substituted as a number.
"""

from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution import ExecutionCommand, ExecutionResult

from accounting.models.ledger import Journal
from accounting.models.stock import StockMovement, StockPosition, StockPosting, StockValueEntry
from accounting.tasks.inventory_reporting import publish


async def capture(db: AsyncSession, command: ExecutionCommand, result: ExecutionResult) -> None:
    if result.outcome != "COMMITTED":
        return
    stock = [effect.effect_id for effect in result.effects if effect.effect_kind == "STOCK"]
    if not stock:
        return
    number = command.voucher_number
    if not number:
        journals = [effect.effect_id for effect in result.effects if effect.effect_kind == "JOURNAL"]
        if len(journals) != 1:
            # Legacy stock commands may have no issued number or posted journal.
            # Retain their original wire; a verified backfill is needed for history.
            return
        journal = await db.scalar(
            select(Journal).where(
                Journal.company_id == command.company_id,
                Journal.id == journals[0],
            )
        )
        if journal is None or journal.status != "POSTED" or not journal.number:
            raise ConflictError("inventory reporting requires its posted journal number")
        number = journal.number
    if len(stock) != 1 or result.committed_generation is None:
        raise ConflictError("inventory reporting requires one committed native stock effect")
    posting = await db.scalar(
        select(StockPosting).where(
            StockPosting.company_id == command.company_id,
            StockPosting.id == stock[0],
        )
    )
    if posting is None or posting.execution_id != command.execution_id:
        raise ConflictError("inventory movement source differs from its committed execution")
    rows = (
        await db.execute(
            select(StockMovement, StockPosition, StockValueEntry)
            .select_from(StockMovement)
            .join(StockPosition, StockPosition.id == StockMovement.position_id)
            .join(StockValueEntry, StockValueEntry.movement_id == StockMovement.id)
            .where(
                StockMovement.company_id == command.company_id,
                StockPosition.company_id == command.company_id,
                StockValueEntry.company_id == command.company_id,
                StockMovement.posting_id == posting.id,
            )
            .order_by(StockMovement.id)
            .limit(201)
        )
    ).all()
    if not rows or len(rows) > 200:
        raise ConflictError("inventory movement handoff exceeds its native execution bound")
    records = []
    for ordinal, (movement, position, value) in enumerate(rows, 1):
        action = "RECEIPT" if posting.action == "PURCHASE_INVOICE" else posting.action
        transfer = None
        if action in {"TRANSFER", "TRANSFER_DISPATCH", "TRANSFER_RECEIPT"}:
            action = "TRANSFER_IN" if movement.leg == "IN" else "TRANSFER_OUT"
            transfer = posting.id
            if posting.action == "TRANSFER_RECEIPT":
                source = await db.scalar(
                    select(StockMovement).where(
                        StockMovement.company_id == command.company_id,
                        StockMovement.id == movement.source_movement_id,
                    )
                )
                if source is None:
                    raise ConflictError("shipment report requires its retained transfer identity")
                transfer = source.posting_id
        sequence = result.committed_generation * 1000 + ordinal
        if sequence > 9_223_372_036_854_775_807:
            raise ConflictError("inventory movement ordering exceeds its storage bound")
        records.append(
            (
                movement.id,
                {
                    "payload": {
                        "kind": "MOVEMENT",
                        "movement_id": str(movement.id),
                        "position_id": str(position.id),
                        "item_id": str(position.item_id),
                        "location_id": str(position.warehouse_id),
                        "effective_date": posting.stock_date.isoformat(),
                        "sequence": sequence,
                        "action": action,
                        "voucher_id": str(command.voucher_id),
                        "line_id": str(movement.line_id),
                        "voucher_number": number,
                        "lot_id": str(position.lot_id) if position.lot_id else None,
                        "quantity_delta": str(movement.quantity),
                        "value_delta": str(value.amount),
                        "transfer_id": str(transfer) if transfer else None,
                    }
                },
            )
        )
    await publish(db, tenant=command.tenant_id, company=command.company_id, records=records)
