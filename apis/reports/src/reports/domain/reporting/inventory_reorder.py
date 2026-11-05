"""Replenishment bands keep their own warehouse scope and exact ordering constraints."""

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reports.domain.reporting.inventory import Inventory


def calculate(stock: "Inventory", parameters: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    basis = parameters.get("quantity_basis", "AVAILABLE")
    if basis == "AVAILABLE" and not stock.coverage.reservations_complete:
        raise ValueError("reorder requires complete available stock evidence")
    if parameters["include_orders"] and not stock.coverage.orders_complete:
        raise ValueError("complete order supply/demand evidence is unavailable")
    if parameters["include_orders"] and parameters.get("location_id"):
        raise ValueError("location-specific order supply/demand evidence is unavailable")
    rows, configured = [], 0
    search = parameters.get("search", "").strip().casefold()
    for identity, item in sorted(stock.items.items()):
        if (
            (parameters.get("item_id")
            and parameters["item_id"] != identity)
            or (parameters.get("group_id")
            and parameters["group_id"] not in stock.memberships[identity])
            or (not parameters.get("include_inactive", True)
            and not item.active)
        ):
            continue
        if search and not any(search in value.casefold() for value in (item.code, item.name)):
            continue
        policies = [policy.model_dump(mode="json") for policy in item.replenishment]
        if not policies and item.reorder_level is not None:
            policies = [
                {
                    "location_id": None,
                    "reorder_level": item.reorder_level,
                    "target_level": item.target_level or item.reorder_level,
                    "minimum_order": item.minimum_order or "0",
                }
            ]
        for policy in policies:
            location = policy.get("location_id")
            if location and location not in stock.locations:
                raise ValueError("replenishment warehouse is absent from the frozen source")
            selected_location = parameters.get("location_id")
            if selected_location and (
                location is None or selected_location not in stock.location_tree[location]
            ):
                continue
            if parameters.get("owner") not in {None, "OWN"}:
                continue
            configured += 1
            selected = stock.selected(
                parameters
                | {"item_id": identity, "location_id": location, "owner": "OWN", "custody": "LOCAL"}
            )
            summary = stock.zero_items(
                stock.summary(selected, "item_id"),
                {"item_id": identity, "owner": "OWN", "custody": "LOCAL"},
            )
            row = next(
                row for row in summary if row["owner"] == "OWN" and row["custody"] == "LOCAL"
            )
            available = Decimal(row["available" if basis == "AVAILABLE" else "eligible"])
            if parameters["include_orders"]:
                if location is not None:
                    raise ValueError(
                        "location-specific order supply/demand evidence is unavailable"
                    )
                if item.pending_supply is None or item.pending_demand is None:
                    raise ValueError("item order coverage is incomplete")
                available += Decimal(item.pending_supply) - Decimal(item.pending_demand)
            shortage = max(Decimal(0), Decimal(policy["reorder_level"]) - available)
            if parameters["only_shortages"] and not shortage:
                continue
            needed = max(Decimal(0), Decimal(policy["target_level"]) - available)
            suggested = max(needed, Decimal(policy["minimum_order"])) if needed else Decimal(0)
            multiple, maximum = policy.get("order_multiple"), policy.get("maximum_order")
            if suggested and multiple:
                increment = Decimal(multiple)
                suggested = (suggested / increment).to_integral_value(
                    rounding=ROUND_CEILING
                ) * increment
            if maximum is not None and suggested > Decimal(maximum):
                suggested = Decimal(maximum)
                if multiple:
                    suggested = (suggested / Decimal(multiple)).to_integral_value(
                        rounding=ROUND_FLOOR
                    ) * Decimal(multiple)
                if suggested < Decimal(policy["minimum_order"]):
                    raise ValueError(
                        "the maximum order cannot satisfy the minimum and order multiple"
                    )
            rows.append(
                row
                | {
                    "policy_id": policy.get("policy_id"),
                    "location_id": location,
                    "location_name": stock.locations[location].name
                    if location
                    else "All warehouses",
                    "quantity_basis": basis,
                    "projected_available": format(available, ".4f"),
                    "reorder_level": policy["reorder_level"],
                    "target_level": policy["target_level"],
                    "minimum_order": policy["minimum_order"],
                    "maximum_order": maximum,
                    "order_multiple": multiple,
                    "shortage": format(shortage, ".4f"),
                    "suggested_quantity": format(suggested, ".4f"),
                    "shortfall_after_order": format(max(Decimal(0), needed - suggested), ".4f"),
                    "orders_status": "COMPLETE" if parameters["include_orders"] else "NOT_INCLUDED",
                }
            )
    return rows, configured
