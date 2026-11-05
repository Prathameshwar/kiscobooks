"""Bounded Catalog-to-Accounting stock facts and delegated source-fence contract.

This private owner evidence is not a browser-submitted stock balance or a claim
that Catalog owns physical stock. Its transport must authenticate both owners.
"""

import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import Field, StrictBool, model_validator

from voucher_execution.contracts import Contract, DelegatedAuthority
from voucher_execution.opening import OpeningUnitFact
from voucher_execution.quantity import QuantityUnitFact
from voucher_execution.stock import Exact

StockOperation = Literal[
    "SALE_ISSUE",
    "PURCHASE_RECEIPT",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "CUSTOMER_RETURN_RECEIPT",
    "SUPPLIER_RETURN_ISSUE",
    "OPENING_STOCK",
    "ADJUSTMENT",
]


class StockItemWarehouseFact(Contract):
    warehouse_id: uuid.UUID
    allowed_operations: tuple[StockOperation, ...] = Field(max_length=8)


class ItemPurchaseTaxFact(Contract):
    """The item's published purchase GST classification and rule on the stock date.

    Catalog resolves it (item, then family, then group); Accounting checks the rule and its
    dated rates against its own replica. It carries identities only, never a rate.
    """

    classification_id: uuid.UUID
    classification_version: int = Field(strict=True, ge=1)
    code: str = Field(pattern=r"^[0-9]{4,8}$")
    rule_id: uuid.UUID
    rule_version: int = Field(strict=True, ge=1)
    treatment: Literal["TAXABLE", "NIL_RATED", "EXEMPT", "NON_GST"]


class StockItemFact(Contract):
    item_id: uuid.UUID
    family_id: uuid.UUID
    item_version: int = Field(strict=True, ge=1)
    family_version: int = Field(strict=True, ge=1)
    status: Literal["ACTIVE", "DISCONTINUED"]
    family_status: Literal["ACTIVE", "DISCONTINUED"]
    kind: Literal["GOODS"] = "GOODS"
    base_unit_id: uuid.UUID
    quantity_increment: Exact = Field(gt=0)
    quantity_decimal_places: int = Field(strict=True, ge=0, le=4)
    profile_id: uuid.UUID
    profile_revision_id: uuid.UUID
    lot_tracking: StrictBool
    serial_tracking: StrictBool
    expiry_required: StrictBool
    manufacture_date_required: StrictBool
    shelf_life_days: int | None = Field(ge=1, le=36500)
    minimum_remaining_life_days: int | None = Field(ge=0, le=36500)
    issue_strategy: Literal["FIFO", "FEFO"]
    valuation_method: Literal["FIFO", "MOVING_AVERAGE", "SPECIFIC"]
    negative_stock_policy: Literal["BLOCK", "WARN", "ALLOW"]
    sellable: StrictBool
    purchasable: StrictBool
    allowed_warehouse_ids: tuple[uuid.UUID, ...] | None = Field(max_length=1000)
    warehouse_permissions: tuple[StockItemWarehouseFact, ...] = Field(max_length=201)
    opening_units: tuple[OpeningUnitFact, ...] = Field(default=(), max_length=100)
    quantity_units: tuple[QuantityUnitFact, ...] = Field(
        default=(), max_length=100, exclude_if=lambda value: not value
    )
    # Present when the request asks for it (a purchase bill) and the item has one.
    purchase_tax: ItemPurchaseTaxFact | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    # Present when the request asks for labels and this actor may read the unit's symbol.
    base_unit_label: str | None = Field(
        default=None, min_length=1, max_length=20, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def distinct_opening_units(self) -> Self:
        if len({row.revision_id for row in self.quantity_units}) != len(self.quantity_units) or any(
            row.item_id != self.item_id for row in self.quantity_units
        ):
            raise ValueError("quantity unit proof belongs to its item with distinct revisions")
        if len({row.revision_id for row in self.opening_units}) != len(self.opening_units) or any(
            row.item_id != self.item_id for row in self.opening_units
        ):
            raise ValueError("opening unit proof must belong to its item with distinct revisions")
        return self


class StockWarehouseFact(Contract):
    warehouse_id: uuid.UUID
    row_version: int = Field(strict=True, ge=1)
    kind: Literal["STORE", "GODOWN", "INTERNAL_TRANSIT"]
    is_active: StrictBool
    department_id: uuid.UUID | None
    policy_revision_id: uuid.UUID
    allowed_operations: tuple[StockOperation, ...] = Field(max_length=8)


class StockBinFact(Contract):
    bin_id: uuid.UUID
    warehouse_id: uuid.UUID
    row_version: int = Field(strict=True, ge=1)
    is_active: StrictBool


class StockFenceRequest(Contract):
    version: Literal[1] = 1
    purpose: Literal["PREVIEW", "EXECUTION"] = "EXECUTION"
    action: Literal["POST", "REVERSE"] = "POST"
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    execution_id: uuid.UUID
    actor_user_id: uuid.UUID
    authority: DelegatedAuthority = Field(repr=False)
    authority_expires_at: dt.datetime
    stock_date: dt.date = Field(ge=dt.date(1000, 1, 1))
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    item_ids: tuple[uuid.UUID, ...] = Field(min_length=1, max_length=100)
    warehouse_ids: tuple[uuid.UUID, ...] = Field(min_length=1, max_length=200)
    bin_ids: tuple[uuid.UUID, ...] = Field(default=(), max_length=200)
    opening_unit_revision_ids: tuple[uuid.UUID, ...] = Field(default=(), max_length=100)
    quantity_unit_revision_ids: tuple[uuid.UUID, ...] = Field(
        default=(), max_length=100, exclude_if=lambda value: not value
    )
    # A purchase bill asks for each item's purchase GST classification and rule.
    include_purchase_tax: StrictBool = Field(default=False, exclude_if=lambda value: not value)
    # A print asks for the labels a person reads (the base unit's symbol); stock never uses them.
    include_labels: StrictBool = Field(default=False, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def bounded_scope(self) -> Self:
        references = (
            self.tenant_id,
            self.company_id,
            self.execution_id,
            self.actor_user_id,
        )
        if any(not value.int for value in references):
            raise ValueError("stock source authority needs real scoped references")
        for values in (
            self.item_ids,
            self.warehouse_ids,
            self.bin_ids,
            self.opening_unit_revision_ids,
            self.quantity_unit_revision_ids,
        ):
            if len(set(values)) != len(values) or any(not value.int for value in values):
                raise ValueError("source references must be real and distinct")
        if self.authority_expires_at.tzinfo is None:
            raise ValueError("stock source authority needs an aware expiry")
        return self


class StockFenceFacts(Contract):
    version: Literal[1] = 1
    purpose: Literal["PREVIEW", "EXECUTION"] = "EXECUTION"
    action: Literal["POST", "REVERSE"] = "POST"
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    execution_id: uuid.UUID
    actor_user_id: uuid.UUID
    fence_id: uuid.UUID
    stock_date: dt.date
    issued_at: dt.datetime
    expires_at: dt.datetime
    policy_generation: int = Field(strict=True, ge=1)
    source_version: int = Field(strict=True, ge=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    items: tuple[StockItemFact, ...] = Field(min_length=1, max_length=100)
    warehouses: tuple[StockWarehouseFact, ...] = Field(min_length=1, max_length=201)
    bins: tuple[StockBinFact, ...] = Field(default=(), max_length=200)

    @model_validator(mode="after")
    def closed_source(self) -> Self:
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("stock source times must be aware")
        if not dt.timedelta(0) < self.expires_at - self.issued_at <= dt.timedelta(seconds=60):
            raise ValueError("stock source fence exceeds its native lifetime")
        for values in (
            [row.item_id for row in self.items],
            [row.warehouse_id for row in self.warehouses],
            [row.bin_id for row in self.bins],
        ):
            if len(set(values)) != len(values) or any(not value.int for value in values):
                raise ValueError("source facts must have distinct real identities")
        if any(
            row.warehouse_id not in {entry.warehouse_id for entry in self.warehouses}
            for row in self.bins
        ):
            raise ValueError("bin facts need their native warehouse")
        return self
