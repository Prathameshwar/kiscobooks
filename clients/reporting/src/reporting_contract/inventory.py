"""Typed stock evidence published by Accounting, independent of operational stock writes."""

import datetime as dt
import uuid
from typing import Annotated, Any, Literal, Self
from zoneinfo import ZoneInfo

from billing_platform.exact import exact_decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")


Amount = Annotated[str, Field(pattern=r"^-?\d{1,15}(\.\d{1,4})?$")]
Positive = Annotated[str, Field(pattern=r"^\d{1,15}(\.\d{1,4})?$")]


class Coverage(Evidence):
    kind: Literal["COVERAGE"] = "COVERAGE"
    as_of: dt.date
    history_start: dt.date
    classification_date: dt.date
    timezone: str = Field(max_length=80)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    complete_company: Literal[True]
    native_stock_current: bool = True
    captured_at: dt.datetime | None = None
    item_count: int = Field(ge=0)
    location_count: int = Field(ge=0)
    group_count: int = Field(ge=0)
    position_count: int = Field(ge=0)
    movement_count: int = Field(ge=0)
    movements_complete: bool
    valuation_complete: bool
    reservations_complete: bool
    orders_complete: bool
    origins_complete: bool
    gl_complete: bool
    serial_history_complete: bool = False

    @model_validator(mode="after")
    def ordered(self) -> Self:
        ZoneInfo(self.timezone)
        if self.history_start > self.as_of or self.classification_date > self.as_of:
            raise ValueError("inventory coverage dates differ")
        return self


class Replenishment(Evidence):
    policy_id: uuid.UUID
    location_id: uuid.UUID | None = None
    reorder_level: Positive
    target_level: Positive
    minimum_order: Positive
    maximum_order: Positive | None = None
    order_multiple: Positive

    @model_validator(mode="after")
    def thresholds(self) -> Self:
        if (
            exact_decimal(self.target_level) < exact_decimal(self.reorder_level)
            or exact_decimal(self.minimum_order) <= 0
            or exact_decimal(self.order_multiple) <= 0
            or self.maximum_order is not None
            and exact_decimal(self.maximum_order) < exact_decimal(self.minimum_order)
        ):
            raise ValueError("invalid replenishment constraints")
        return self


class Item(Evidence):
    kind: Literal["ITEM"] = "ITEM"
    item_id: uuid.UUID
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    unit: str = Field(min_length=1, max_length=30)
    group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=64)
    active: bool
    lot_tracked: bool
    serial_tracked: bool
    minimum_remaining_days: int = Field(default=0, ge=0, le=36500)
    reorder_level: Positive | None = None
    target_level: Positive | None = None
    minimum_order: Positive | None = None
    pending_supply: Positive | None = None
    pending_demand: Positive | None = None
    replenishment: list[Replenishment] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def thresholds(self) -> Self:
        if len({row.location_id for row in self.replenishment}) != len(
            self.replenishment
        ) or len({row.policy_id for row in self.replenishment}) != len(
            self.replenishment
        ):
            raise ValueError("duplicate replenishment scope")
        if len(self.group_ids) != len(set(self.group_ids)):
            raise ValueError("duplicate item classification")
        if self.target_level is not None and (
            self.reorder_level is None
            or exact_decimal(self.target_level) < exact_decimal(self.reorder_level)
        ):
            raise ValueError("target must be at least the reorder level")
        return self


class Location(Evidence):
    kind: Literal["LOCATION"] = "LOCATION"
    location_id: uuid.UUID
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None


class Group(Evidence):
    kind: Literal["GROUP"] = "GROUP"
    group_id: uuid.UUID
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None


class CostLayer(Evidence):
    """Owner's residual FIFO layer allocated to one stock position at the cutoff."""

    layer_id: uuid.UUID
    origin_id: uuid.UUID | None = None
    receipt_date: dt.date
    quantity: Positive
    carrying_value: Positive


class CostPool(Evidence):
    """This position's share of an owner moving-average pool, never the pool total."""

    pool_id: uuid.UUID
    quantity: Positive
    carrying_value: Positive


class ValuationDetail(Evidence):
    layers: list[CostLayer] = Field(default_factory=list, max_length=200)
    pool: CostPool | None = None


class Position(Evidence):
    kind: Literal["POSITION"] = "POSITION"
    position_id: uuid.UUID
    item_id: uuid.UUID
    location_id: uuid.UUID
    bin_id: uuid.UUID | None = None
    owner: Literal["OWN", "THIRD_PARTY"]
    owner_party_id: uuid.UUID | None = None
    custody: Literal["LOCAL", "TRANSIT", "EXTERNAL"]
    custodian_id: uuid.UUID | None = None
    lot_id: uuid.UUID | None = None
    lot_code: str | None = Field(default=None, max_length=120)
    manufacture_date: dt.date | None = None
    expiry_date: dt.date | None = None
    expiry_day_usable: bool = False
    minimum_remaining_days: int = Field(default=0, ge=0, le=36500)
    disposition: Literal["GOOD", "HELD", "DAMAGED", "QUARANTINE"]
    quantity: Positive
    eligible_quantity: Positive | None = None
    opening_quantity: Positive
    inward_quantity: Positive
    outward_quantity: Positive
    reserved: Positive | None
    carrying_value: Positive | None
    costing_method: Literal["FIFO", "MOVING_AVERAGE"] | None
    control_account_id: uuid.UUID | None = None
    valuation_detail: ValuationDetail | None = None
    # Residual origin cohorts, not cost layers. Transfer preserves the original receipt date.
    origins: list["Origin"] = Field(default_factory=list, max_length=200)
    serials: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        quantity = exact_decimal(self.quantity)
        if (
            self.eligible_quantity is not None
            and exact_decimal(self.eligible_quantity) > quantity
        ):
            raise ValueError("eligible stock exceeds physical quantity")
        if (
            exact_decimal(self.opening_quantity)
            + exact_decimal(self.inward_quantity)
            - exact_decimal(self.outward_quantity)
            != quantity
        ):
            raise ValueError("position opening and turnover do not reconcile")
        if self.reserved is not None and exact_decimal(self.reserved) > quantity:
            raise ValueError("reservation exceeds physical quantity")
        if self.carrying_value is not None and self.costing_method is None:
            raise ValueError("value requires an owner costing method")
        if (
            self.manufacture_date
            and self.expiry_date
            and self.manufacture_date > self.expiry_date
        ):
            raise ValueError("manufacture date follows expiry date")
        if (self.lot_id is None) != (self.lot_code is None):
            raise ValueError("lot identity and code must be supplied together")
        if len(self.serials) != len(set(self.serials)):
            raise ValueError("duplicate serial identity")
        if self.valuation_detail is not None:
            from decimal import Decimal, localcontext

            detail = self.valuation_detail
            if self.owner != "OWN" or self.carrying_value is None:
                raise ValueError("valuation cost detail requires owned stock value")
            if self.costing_method == "FIFO":
                if detail.pool is not None or len(
                    {r.layer_id for r in detail.layers}
                ) != len(detail.layers):
                    raise ValueError(
                        "FIFO cost layers contain a pool or duplicate layer"
                    )
                with localcontext() as arithmetic:
                    arithmetic.prec = 48
                    layer_quantity = sum(
                        (Decimal(r.quantity) for r in detail.layers), Decimal(0)
                    )
                    layer_value = sum(
                        (Decimal(r.carrying_value) for r in detail.layers), Decimal(0)
                    )
                if layer_quantity != quantity or layer_value != exact_decimal(
                    self.carrying_value
                ):
                    raise ValueError(
                        "FIFO cost layers do not reconcile to position quantity/value"
                    )
            elif (
                self.costing_method != "MOVING_AVERAGE"
                or detail.layers
                or detail.pool is None
                or exact_decimal(detail.pool.quantity) != quantity
                or exact_decimal(detail.pool.carrying_value)
                != exact_decimal(self.carrying_value)
            ):
                raise ValueError(
                    "moving-average cost pool does not reconcile to position"
                )
        return self


class Origin(Evidence):
    origin_id: uuid.UUID
    receipt_date: dt.date | None
    manufacture_date: dt.date | None = None
    provenance: Literal["KNOWN", "ASSUMED", "UNKNOWN"]
    quantity: Positive


class Movement(Evidence):
    kind: Literal["MOVEMENT"] = "MOVEMENT"
    movement_id: uuid.UUID
    position_id: uuid.UUID
    item_id: uuid.UUID
    location_id: uuid.UUID
    effective_date: dt.date
    # Company-wide stable leg order within the effective date, including paired transfers.
    sequence: int = Field(ge=1)
    action: Literal[
        "OPENING",
        "RECEIPT",
        "SALE",
        "CONSUMPTION",
        "CUSTOMER_RETURN",
        "SUPPLIER_RETURN",
        "TRANSFER_IN",
        "TRANSFER_OUT",
        "COUNT",
        "DISPOSAL",
        "VALUE_ADJUSTMENT",
        "DISPATCH",
        "REVERSAL",
    ]
    voucher_id: uuid.UUID
    # Native stock line identity permits exact invoice-to-cost attribution.
    line_id: uuid.UUID | None = None
    voucher_number: str = Field(min_length=1, max_length=120)
    lot_id: uuid.UUID | None = None
    quantity_delta: Amount
    value_delta: Amount | None
    transfer_id: uuid.UUID | None = None
    origin_id: uuid.UUID | None = None
    serials: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def direction(self) -> Self:
        quantity = exact_decimal(self.quantity_delta)
        positive = {"OPENING", "RECEIPT", "CUSTOMER_RETURN", "TRANSFER_IN"}
        negative = {
            "SALE",
            "CONSUMPTION",
            "SUPPLIER_RETURN",
            "TRANSFER_OUT",
            "DISPOSAL",
        }
        if (self.action in positive and quantity <= 0) or (
            self.action in negative and quantity >= 0
        ):
            raise ValueError("movement direction differs from action")
        if self.action == "VALUE_ADJUSTMENT" and quantity != 0:
            raise ValueError("value adjustment cannot move quantity")
        if self.action in {"DISPATCH", "REVERSAL"} and (
            quantity == 0 or (self.action == "DISPATCH" and quantity > 0)
        ):
            raise ValueError(
                "native dispatch/reversal requires its actual signed quantity"
            )
        if self.action.startswith("TRANSFER_") and self.transfer_id is None:
            raise ValueError("transfer movement requires shared transfer identity")
        return self


class GLControl(Evidence):
    kind: Literal["GL_CONTROL"] = "GL_CONTROL"
    account_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    balance: Amount


Payload = Annotated[
    Coverage | Item | Location | Group | Position | Movement | GLControl,
    Field(discriminator="kind"),
]


class InventoryRecord(Evidence):
    payload: Payload

    @field_validator("payload", mode="before")
    @classmethod
    def bounded(cls, value: Any) -> Any:
        # Transport/page limits provide the byte bound; these contracts bound collections.
        if not isinstance(value, dict | Evidence):
            raise ValueError("typed inventory evidence is required")
        return value
