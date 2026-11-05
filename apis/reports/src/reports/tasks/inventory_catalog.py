"""Inventory registrations use the same durable job, row, navigation and export contracts."""

import uuid
from collections.abc import Mapping
from typing import Any

from reporting_contract.contract import Control, Fact

from reports.domain.reporting.contracts import (
    Column,
    DatasetDefinition,
    Drilldown,
    ReportDefinition,
    ValueKind,
    View,
    fingerprint,
)
from reports.domain.reporting.inventory import CODES, calculate
from reports.domain.reporting.registry import Registration
from reports.schemas import inventory as p
from reports.tasks.access import INPUT_PERMISSIONS
from reports.tasks.report_catalog import ReferenceAdapter

DATASET = DatasetDefinition(
    "inventory",
    1,
    "one owner stock evidence identity at a committed snapshot",
    ("source_id",),
    ("source_id", "item_id", "location_id", "lot_id"),
    ("quantity", "carrying_value"),
    ("STOCK_EFFECTIVE", "AS_OF", "PINNED_CLASSIFICATION"),
)
BASE = ("item_id", "item_code", "item_name", "unit", "owner", "custody", "currency", "as_of")
PLACE = ("location_id", "location_code", "location_name")
BALANCES = (
    "opening",
    "inward",
    "outward",
    "quantity",
    "eligible",
    "reserved",
    "available",
    "reservation_status",
    "carrying_value",
    "valuation_status",
)
OUTPUTS = {
    "STOCK_SUMMARY": BASE + BALANCES,
    "ITEM_LEDGER": BASE
    + PLACE
    + (
        "position_id",
        "lot_id",
        "lot_code",
        "row_kind",
        "date",
        "voucher_number",
        "action",
        "inward",
        "outward",
        "balance",
        "value_delta",
        "value_balance",
    ),
    "LOCATION_STOCK": BASE + PLACE + BALANCES,
    "STOCK_VALUATION": BASE
    + PLACE
    + (
        "position_id",
        "lot_id",
        "lot_code",
        "row_kind",
        "quantity",
        "unit_cost",
        "carrying_value",
        "costing_method",
        "account_id",
        "gl_balance",
        "difference",
        "valuation_detail_status",
        "layer_id",
        "pool_id",
        "origin_id",
        "receipt_date",
        "remaining_quantity",
        "remaining_value",
        "movement_id",
        "voucher_id",
        "voucher_number",
        "date",
        "value_delta",
    ),
    "BATCH_SUMMARY": BASE
    + PLACE
    + (
        "position_id",
        "lot_id",
        "lot_code",
        "quantity",
        "manufacture_date",
        "expiry_date",
        "serial_count",
        "serial",
        "source_position_quantity",
        "serials",
        "origins",
        "row_kind",
        "date",
        "voucher_number",
        "action",
        "movement_quantity",
        "origin_id",
        "transfer_id",
        "source_movement_quantity",
    ),
    "STOCK_EXPIRY": BASE
    + PLACE
    + (
        "lot_id",
        "lot_code",
        "quantity",
        "expiry_date",
        "days_to_expiry",
        "status",
        "eligibility_reasons",
        "carrying_value",
        "valuation_status",
        "reserved",
        "reservation_status",
    ),
    "STOCK_REORDER": (
        *BASE,
        "policy_id",
        "location_id",
        "location_name",
        "quantity_basis",
        "quantity",
        "eligible",
        "available",
        "projected_available",
        "reorder_level",
        "target_level",
        "shortage",
        "suggested_quantity",
        "minimum_order",
        "maximum_order",
        "order_multiple",
        "shortfall_after_order",
        "orders_status",
    ),
    "STOCK_AGEING": BASE
    + PLACE
    + (
        "lot_id",
        "lot_code",
        "origin_id",
        "quantity",
        "origin_date",
        "age_days",
        "age_bucket",
        "age_basis",
        "provenance",
    ),
    "STOCK_MOVEMENT": (
        *BASE,
        "opening",
        "inward",
        "outward",
        "quantity",
        "opening_value",
        "inward_value",
        "outward_value",
        "closing_value",
        "receipts",
        "sales",
        "consumption",
        "customer_returns",
        "supplier_returns",
        "transfer_in",
        "transfer_out",
        "last_consumption_date",
        "days_without_consumption",
        "nonmoving",
        "history_status",
    ),
    "STOCK_GROUP_SUMMARY": (
        "group_id",
        "group_code",
        "group_name",
        "unit",
        "owner",
        "custody",
        "currency",
        "as_of",
        *BALANCES,
    ),
}
MONEY = {
    "carrying_value",
    "unit_cost",
    "value_delta",
    "value_balance",
    "gl_balance",
    "difference",
    "opening_value",
    "inward_value",
    "outward_value",
    "closing_value",
    "remaining_value",
}
QUANTITIES = {
    "remaining_quantity",
    "movement_quantity",
    "source_movement_quantity",
    "source_position_quantity",
    "opening",
    "inward",
    "outward",
    "quantity",
    "eligible",
    "reserved",
    "available",
    "balance",
    "projected_available",
    "reorder_level",
    "target_level",
    "shortage",
    "suggested_quantity",
    "minimum_order",
    "maximum_order",
    "order_multiple",
    "shortfall_after_order",
    "receipts",
    "sales",
    "consumption",
    "customer_returns",
    "supplier_returns",
    "transfer_in",
    "transfer_out",
}


def column(key: str) -> Column:
    kind: ValueKind = (
        "MONEY"
        if key in MONEY
        else "DECIMAL"
        if key in QUANTITIES
        else "IDENTIFIER"
        if key.endswith("_id")
        else "DATE"
        if key.endswith("_date") or key in {"date", "as_of"}
        else "INTEGER"
        if key in {"age_days", "days_to_expiry", "serial_count", "days_without_consumption"}
        else "BOOLEAN"
        if key == "nonmoving"
        else "TEXT"
    )
    return Column(key, key.replace("_", " ").title(), kind, "currency" if key in MONEY else None)


class InventoryAdapter(ReferenceAdapter):
    @property
    def inventory_model(self) -> type[p.InventoryParameters]:
        models: dict[str, type[p.InventoryParameters]] = {
            "STOCK_SUMMARY": p.StockSummaryParameters,
            "LOCATION_STOCK": p.LocationParameters,
            "BATCH_SUMMARY": p.BatchParameters,
            "STOCK_VALUATION": p.ValuationParameters,
            "ITEM_LEDGER": p.LedgerParameters,
            "STOCK_EXPIRY": p.ExpiryParameters,
            "STOCK_AGEING": p.AgeingParameters,
            "STOCK_MOVEMENT": p.MovementParameters,
            "STOCK_REORDER": p.ReorderParameters,
            "STOCK_GROUP_SUMMARY": p.GroupParameters,
        }
        return models.get(self.code, p.InventoryParameters)

    def normalize(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return self.inventory_model.model_validate(values).model_dump(
            mode="json", exclude_none=True
        )

    def parameters(self) -> dict[str, Any]:
        return self.inventory_model.model_json_schema()

    def execute(
        self,
        facts: list[Fact],
        generation_id: uuid.UUID,
        values: Mapping[str, Any],
        control: Control,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return calculate(
            self.code,
            [
                row.data
                for row in facts
                if row.data is not None and row.entity == "inventory_report_record"
            ],
            self.normalize(values),
        )


def registrations(implementation: str) -> list[Registration[ReferenceAdapter]]:
    entries: list[Registration[ReferenceAdapter]] = []
    for code in CODES:
        from reports.schemas.report_parameters import SourceParameters

        handler = InventoryAdapter(code, SourceParameters)
        title = code.replace("_", " ").title()
        output = tuple(column(key) for key in OUTPUTS[code])
        links = [Drilldown("row_detail", "Frozen row detail", code)]
        if code not in {"ITEM_LEDGER", "STOCK_GROUP_SUMMARY"}:
            links.append(Drilldown("stock_item_entries", "Item stock ledger", "ITEM_LEDGER"))
        if code == "STOCK_GROUP_SUMMARY":
            links.append(Drilldown("stock_group_items", "Items in group", "STOCK_SUMMARY"))
        if code == "STOCK_SUMMARY":
            links.append(Drilldown("stock_item_locations", "Warehouses", "LOCATION_STOCK"))
        entries.append(
            Registration(
                ReportDefinition(
                    code=code,
                    version={
                        "STOCK_SUMMARY": 3,
                        "ITEM_LEDGER": 4,
                        "LOCATION_STOCK": 4,
                        "STOCK_VALUATION": 4,
                        "BATCH_SUMMARY": 4,
                        "STOCK_EXPIRY": 4,
                        "STOCK_REORDER": 3,
                        "STOCK_AGEING": 3,
                        "STOCK_MOVEMENT": 4,
                        "STOCK_GROUP_SUMMARY": 3,
                    }[code],
                    title=title,
                    description=f"{title} from complete, policy-pinned Accounting stock evidence.",
                    implementation_hash=implementation,
                    parameter_schema_hash=fingerprint(handler.parameters()),
                    datasets=("inventory",),
                    metrics=(),
                    permissions=tuple(
                        sorted(
                            INPUT_PERMISSIONS
                            | {"item.read", "warehouse.read"}
                            | ({"item_warehouse_policy.read"} if code == "STOCK_REORDER" else set())
                        )
                    ),
                    views=(
                        View(
                            "default",
                            title,
                            tuple(
                                c
                                for c in output
                                if (
                                    (not c.key.endswith("_id") or c.key == "account_id")
                                    and c.key
                                    not in {
                                        "origins",
                                        "serials",
                                        "source_position_quantity",
                                        "source_movement_quantity",
                                    }
                                )
                            ),
                            "REGISTER",
                        ),
                        View("audit", "Source details", output, "REGISTER"),
                    ),
                    resource_class="BULK",
                    drilldowns=tuple(links),
                ),
                handler,
            )
        )
    return entries
