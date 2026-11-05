"""Per-product location policy and replenishment wire types.

Both PUTs state the **whole** policy, the same reason the location's own operation policy
does: an omitted location or an omitted band could neither quietly keep nor quietly drop
what it replaces, and the reviewer approving the change sees exactly what the resolver will
read (docs/catalog-warehouses.md §2).
"""

import uuid
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from catalog.domain.warehouse_policy_composition import (
    LOCATION_LIMIT,
    MAX_LEAD_TIME_DAYS,
    SCOPE_LIMIT,
)
from catalog.domain.warehouse_resolution import ACTIVITY_DEFAULTS
from catalog.schemas.pricing import ExactDecimal, PricingInput, PublicationInput
from catalog.schemas.warehouses import OperationFlagsInput

SelectionMode = Literal["ALLOW_ALL_ACTIVE", "ALLOW_LIST"]


class LocationPermissionInput(OperationFlagsInput):
    """One location this product may be kept at, and the operations allowed there.

    The flags are a narrowing of the location's own reviewed policy, never an addition to
    it: a flag the location does not allow is refused rather than trimmed, so the stored row
    means what the reviewer ticked.
    """

    warehouse_id: uuid.UUID


class ItemWarehousePolicyInput(PublicationInput):
    """The product's whole location policy: the mode, the membership and the defaults.

    Every activity default must also appear in ``locations``. A default pointing at a
    location the product does not explicitly permit would be a permission asserted in one
    column and denied in another, and it is what lets a location deactivation check its
    dependencies with two indexed lookups instead of trusting a scan
    (docs/catalog-warehouses.md §3, §5).
    """

    selection_mode: SelectionMode
    default_sale_warehouse_id: uuid.UUID | None
    default_purchase_warehouse_id: uuid.UUID | None
    default_customer_return_warehouse_id: uuid.UUID | None
    default_opening_warehouse_id: uuid.UUID | None
    locations: list[LocationPermissionInput] = Field(
        default_factory=list, max_length=LOCATION_LIMIT
    )

    @model_validator(mode="after")
    def coherent(self) -> Self:
        named = {entry.warehouse_id for entry in self.locations}
        if len(named) != len(self.locations):
            raise ValueError("a stock location appears twice in the product policy")
        if self.selection_mode == "ALLOW_LIST" and not self.locations:
            raise ValueError("an allowlist names at least one stock location")
        for column in ACTIVITY_DEFAULTS:
            target: uuid.UUID | None = getattr(self, column)
            if target is not None and target not in named:
                raise ValueError("a product activity default must be a permitted stock location")
        return self


class ReplenishmentScopeInput(PricingInput):
    """One reviewed band: at a named location, or for the product as a whole.

    ``warehouse_id`` is ``null`` for the product-wide band. Exactly one such band may exist
    per product — the stored scope key carries a sentinel rather than ``NULL`` so that is a
    unique constraint rather than a convention.
    """

    warehouse_id: uuid.UUID | None
    purchase_binding_id: uuid.UUID
    safety_quantity: ExactDecimal = Field(ge=0)
    reorder_quantity: ExactDecimal = Field(ge=0)
    target_quantity: ExactDecimal = Field(gt=0)
    min_order_quantity: ExactDecimal = Field(gt=0)
    max_order_quantity: ExactDecimal | None = Field(default=None, gt=0)
    order_multiple: ExactDecimal = Field(gt=0)
    lead_time_days: int = Field(strict=True, ge=0, le=MAX_LEAD_TIME_DAYS)


class ItemReplenishmentPolicyInput(PublicationInput):
    """The product's whole set of bands. A scope left out is retired, never left stale."""

    scopes: list[ReplenishmentScopeInput] = Field(default_factory=list, max_length=SCOPE_LIMIT)

    @model_validator(mode="after")
    def one_band_per_scope(self) -> Self:
        keys = [scope.warehouse_id for scope in self.scopes]
        if len(set(keys)) != len(keys):
            raise ValueError("a replenishment scope appears twice")
        return self


class LocationPermissionDetail(BaseModel):
    """One membership row through the caller's read policy.

    Everything but the identity is optional and unset when a field policy denies reading it:
    a read deny holds in projections, not only in forms (docs/field-permissions.md §6). An
    entry whose ``warehouse_id`` is denied is omitted from the view entirely — its flags
    would still disclose that the product is stocked somewhere the reader may not see.
    """

    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    warehouse_id: uuid.UUID | None = None
    is_active: bool | None = None
    allow_sale_issue: bool | None = None
    allow_purchase_receipt: bool | None = None
    allow_transfer_in: bool | None = None
    allow_transfer_out: bool | None = None
    allow_customer_return_receipt: bool | None = None
    allow_supplier_return_issue: bool | None = None
    allow_opening_stock: bool | None = None
    allow_adjustment: bool | None = None
    row_version: int | None = None
    #: The location's own reviewed revision — what this product's flags are narrowed by.
    #: ``null`` when the location has no reviewed policy, which allows nothing.
    location_revision: int | None = None
    #: The composition: operation kinds both the location and this product allow. Unset when
    #: any flag is unreadable, since a partial intersection would read as a denial.
    effective_operations: list[str] | None = None


class ItemWarehousePolicyView(BaseModel):
    """The product's stored policy, or the baseline that its absence means.

    ``is_configured`` is the honest distinction: ``false`` with ``ALLOW_ALL_ACTIVE`` says
    "no row, so the location's own policy decides", never "somebody chose this".
    """

    model_config = ConfigDict(extra="forbid")
    item_id: uuid.UUID
    is_configured: bool
    selection_mode: str | None = None
    default_sale_warehouse_id: uuid.UUID | None = None
    default_purchase_warehouse_id: uuid.UUID | None = None
    default_customer_return_warehouse_id: uuid.UUID | None = None
    default_opening_warehouse_id: uuid.UUID | None = None
    row_version: int | None = None
    policy_generation: int
    source_version: int
    locations: list[LocationPermissionDetail] = Field(default_factory=list)


class ReplenishmentScopeDetail(BaseModel):
    """One band through the caller's read policy. Quantities stay exact on the wire."""

    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    is_item_wide: bool
    warehouse_id: uuid.UUID | None = None
    purchase_binding_id: uuid.UUID | None = None
    safety_quantity: Decimal | None = None
    reorder_quantity: Decimal | None = None
    target_quantity: Decimal | None = None
    min_order_quantity: Decimal | None = None
    max_order_quantity: Decimal | None = None
    order_multiple: Decimal | None = None
    lead_time_days: int | None = None
    is_active: bool | None = None
    row_version: int | None = None


class ItemReplenishmentPolicyView(BaseModel):
    """The product's reviewed bands. No on-hand quantity appears here: Catalog owns none."""

    model_config = ConfigDict(extra="forbid")
    item_id: uuid.UUID
    policy_generation: int
    source_version: int
    scopes: list[ReplenishmentScopeDetail] = Field(default_factory=list)
