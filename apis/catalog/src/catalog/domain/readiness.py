"""Actual implementation/source status, not fabricated company feature state.

Identity publishes a complete versioned Catalog source contract. Company readiness
still requires its verified local snapshot and unexpired lease. Billing source APIs
do not exist. Keep the dependency contract explicit;
never infer source readiness from a successful database connection or an environment flag.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class SourceRequirement:
    key: str
    owner: Literal["identity", "billing"]
    contract_version: int | None = None
    status: Literal["unavailable"] = "unavailable"


SOURCE_REQUIREMENTS = (
    SourceRequirement("company_and_features", "identity", contract_version=1),
    SourceRequirement("field_definitions_and_policies", "identity", contract_version=1),
    SourceRequirement("parties_and_customer_types", "billing"),
    SourceRequirement("physical_lots_and_price_declarations", "billing"),
    SourceRequirement("policy_consumer_acknowledgement", "billing"),
    # Stock quantity, value, reservation and pending-document facts behind the
    # location guards. Catalog cannot check them and must not infer them: a
    # non-Main deactivation stays unavailable while this is unavailable
    # (docs/catalog-warehouses.md §5).
    SourceRequirement("warehouse_stock_and_location_guards", "billing"),
)


@dataclass(frozen=True, slots=True)
class Capability:
    key: str
    phase: str
    implemented: bool = False


CAPABILITIES = (
    Capability("unit_and_pack_definitions", "C6", implemented=True),
    Capability("product_definitions", "C7", implemented=True),
    Capability("commercial_prices", "C8", implemented=True),
    Capability("tax_definitions", "C9", implemented=True),
    Capability("catalog_bulk_operations", "C10", implemented=True),
    # Locations, groups, bins, operation policies and SKU location policies.
    # Definitions only; operational enforcement belongs to the source requirement
    # above, so a client sees this ready while enforcement stays pending.
    Capability("stock_location_definitions", "C7", implemented=True),
    Capability("manufacturing_operation_definitions", "M0", implemented=True),
    Capability("manufacturing_route_definitions", "M0", implemented=True),
    Capability("promotion_definitions", "P1"),
    Capability("bom_definitions", "M0-M4"),
)
