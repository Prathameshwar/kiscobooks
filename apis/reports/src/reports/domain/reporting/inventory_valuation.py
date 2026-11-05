"""Owner cost detail uses separate measures so detail rows cannot multiply balances."""

from typing import TYPE_CHECKING, Any

from reporting_contract.inventory import Position

if TYPE_CHECKING:
    from reports.domain.reporting.inventory import Inventory


def detail_rows(stock: "Inventory", selected: list[Position]) -> list[dict[str, Any]]:
    from reports.domain.reporting.inventory import fixed, number

    if not stock.movements_loaded or not stock.coverage.movements_complete:
        raise ValueError("valuation cost detail requires complete retained movement history")
    owned = {str(p.position_id): p for p in selected if p.owner == "OWN"}
    rows: list[dict[str, Any]] = []
    for _key, position in sorted(owned.items()):
        detail = position.valuation_detail
        if detail is None:
            raise ValueError("complete owner valuation cost detail is unavailable")
        label = stock.label(position) | {
            "costing_method": position.costing_method,
            "account_id": str(position.control_account_id) if position.control_account_id else None,
        }
        for layer in sorted(detail.layers, key=lambda r: (r.receipt_date, str(r.layer_id))):
            rows.append(
                label
                | {
                    "row_kind": "COST_LAYER",
                    "layer_id": str(layer.layer_id),
                    "origin_id": str(layer.origin_id) if layer.origin_id else None,
                    "receipt_date": layer.receipt_date.isoformat(),
                    "remaining_quantity": fixed(number(layer.quantity)),
                    "remaining_value": fixed(number(layer.carrying_value)),
                }
            )
        if detail.pool is not None:
            rows.append(
                label
                | {
                    "row_kind": "COST_POOL",
                    "pool_id": str(detail.pool.pool_id),
                    "remaining_quantity": fixed(number(detail.pool.quantity)),
                    "remaining_value": fixed(number(detail.pool.carrying_value)),
                }
            )
    for movement in sorted(
        stock.movements, key=lambda r: (r.effective_date, r.sequence, str(r.movement_id))
    ):
        if str(movement.position_id) not in owned or movement.action != "VALUE_ADJUSTMENT":
            continue
        rows.append(
            stock.label(owned[str(movement.position_id)])
            | {
                "row_kind": "VALUE_ADJUSTMENT",
                "movement_id": str(movement.movement_id),
                "voucher_id": str(movement.voucher_id),
                "voucher_number": movement.voucher_number,
                "date": movement.effective_date.isoformat(),
                "value_delta": fixed(number(movement.value_delta)),
            }
        )
    return rows
