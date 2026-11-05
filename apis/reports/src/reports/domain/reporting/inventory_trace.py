"""Lot and individual-unit history from retained movements, with separate balance/flow grains."""

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from reporting_contract.inventory import Position

if TYPE_CHECKING:
    from reports.domain.reporting.inventory import Inventory


def verify_units(stock: "Inventory", item_ids: set[str]) -> None:
    held: dict[tuple[str, str], str] = {}
    for movement in sorted(
        stock.movements,
        key=lambda m: (
            m.effective_date,
            m.sequence,
            str(m.movement_id),
        ),
    ):
        if str(movement.item_id) not in item_ids:
            continue
        units = {serial.casefold() for serial in movement.serials}
        quantity = Decimal(movement.quantity_delta)
        if len(units) != len(movement.serials) or Decimal(len(units)) != abs(quantity):
            raise ValueError("serial movement identities do not reconcile to quantity")
        for serial in units:
            key = (str(movement.item_id), serial)
            if quantity > 0:
                if key in held:
                    raise ValueError("serial movement duplicates an already-held unit")
                held[key] = str(movement.position_id)
            else:
                if held.get(key) != str(movement.position_id):
                    raise ValueError(
                        "serial movement identities do not reconcile to retained unit state"
                    )
                del held[key]
    expected = {
        (str(position.item_id), serial.casefold()): str(position.position_id)
        for position in stock.positions.values()
        if str(position.item_id) in item_ids
        for serial in position.serials
    }
    if held != expected:
        raise ValueError("serial movement identities do not reconcile to current positions")


def history(
    stock: "Inventory", positions: list[Position], p: dict[str, Any]
) -> list[dict[str, Any]]:
    if not stock.coverage.movements_complete:
        raise ValueError("complete retained stock movement history is unavailable")
    serial = p.get("serial")
    positions = [
        position
        for position in positions
        if (
            stock.items[str(position.item_id)].lot_tracked
            or stock.items[str(position.item_id)].serial_tracked
        )
    ]
    serial_items = {
        str(position.item_id)
        for position in positions
        if stock.items[str(position.item_id)].serial_tracked
    }
    if serial_items and not stock.coverage.serial_history_complete:
        raise ValueError("complete serial movement history is unavailable")
    if serial_items:
        verify_units(stock, serial_items)
    selected = {str(position.position_id) for position in positions}
    rows = []
    for movement in sorted(
        stock.movements,
        key=lambda m: (
            m.effective_date,
            m.sequence,
            str(m.movement_id),
        ),
    ):
        if str(movement.position_id) not in selected:
            continue
        if serial and serial.casefold() not in {s.casefold() for s in movement.serials}:
            continue
        rows.append(
            stock.label(stock.positions[str(movement.position_id)])
            | {
                "row_kind": "BATCH_MOVEMENT",
                "date": movement.effective_date.isoformat(),
                "movement_id": str(movement.movement_id),
                "voucher_id": str(movement.voucher_id),
                "voucher_number": movement.voucher_number,
                "action": movement.action,
                "movement_quantity": (
                    "1.0000" if Decimal(movement.quantity_delta) > 0 else "-1.0000"
                )
                if serial
                else movement.quantity_delta,
                "source_movement_quantity": movement.quantity_delta,
                "serial": next(
                    (
                        value
                        for value in movement.serials
                        if serial and value.casefold() == serial.casefold()
                    ),
                    None,
                ),
                "serials": ", ".join(
                    s for s in movement.serials if not serial or s.casefold() == serial.casefold()
                ),
                "origin_id": str(movement.origin_id) if movement.origin_id else None,
                "transfer_id": str(movement.transfer_id) if movement.transfer_id else None,
            }
        )
    return rows
