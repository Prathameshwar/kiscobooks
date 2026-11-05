"""Typed physical effects; money, identities and custody are never free-form fields."""

import datetime as dt
import uuid
from typing import Any, Literal, Self

from pydantic import (
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from voucher_execution.contracts import Contract
from voucher_execution.count import CountCapture
from voucher_execution.opening import OpeningCapture
from voucher_execution.quantity import QuantityCapture
from voucher_execution.stock_decimal import Exact as Exact

StockAction = Literal[
    "OPENING",
    "RECEIPT",
    "DISPATCH",
    "TRANSFER",
    "TRANSFER_DISPATCH",
    "TRANSFER_RECEIPT",
    "CUSTOMER_RETURN",
    "SUPPLIER_RETURN",
    "COUNT",
    # B24: a Purchase bill that brings its goods into stock at Accounting's landed cost.
    "PURCHASE_INVOICE",
]

STOCK_PROFILES: dict[str, tuple[str, str]] = {
    "OPENING": ("STOCK_JOURNAL", "OPENING"),
    "RECEIPT": ("RECEIPT_NOTE", "STANDARD"),
    "DISPATCH": ("DELIVERY_NOTE", "STANDARD"),
    "TRANSFER": ("STOCK_JOURNAL", "TRANSFER"),
    "TRANSFER_DISPATCH": ("STOCK_JOURNAL", "TRANSFER_DISPATCH"),
    "TRANSFER_RECEIPT": ("STOCK_JOURNAL", "TRANSFER_RECEIPT"),
    "CUSTOMER_RETURN": ("REJECTIONS_IN", "STANDARD"),
    "SUPPLIER_RETURN": ("REJECTIONS_OUT", "STANDARD"),
    "COUNT": ("PHYSICAL_STOCK", "STANDARD"),
    "PURCHASE_INVOICE": ("PURCHASE", "STANDARD"),
}


class StockPolicy(Contract):
    allow_zero_value_receipts: StrictBool = False
    opening_gl_mode: Literal["COMBINED", "LINKED_GL", "EITHER"] = "EITHER"


class StockLine(Contract):
    line_id: uuid.UUID
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID | None = None
    lot_id: uuid.UUID | None = None
    unit_ids: tuple[uuid.UUID, ...] = Field(default=(), max_length=200)
    quantity: Exact = Field(ge=0)
    received_value: Exact | None = Field(default=None, ge=0)
    zero_value_reason: str | None = Field(default=None, min_length=3, max_length=500)
    destination_warehouse_id: uuid.UUID | None = None
    destination_bin_id: uuid.UUID | None = None
    source_movement_id: uuid.UUID | None = None
    opening_journal_line_id: uuid.UUID | None = None
    opening: OpeningCapture | None = Field(default=None, exclude_if=lambda value: value is None)
    quantity_entry: QuantityCapture | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    count: CountCapture | None = Field(default=None, exclude_if=lambda value: value is None)

    @field_validator("zero_value_reason")
    @classmethod
    def reviewed_zero_reason(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if len(value) < 3 or any(ord(character) < 32 for character in value):
                raise ValueError("zero-cost evidence must be a printable meaningful reason")
        return value

    @field_validator("*")
    @classmethod
    def real_reference(cls, value: Any) -> Any:
        if isinstance(value, uuid.UUID) and value.int == 0:
            raise ValueError("use a real owner reference, never a canonical sentinel")
        return value

    @model_validator(mode="after")
    def identifiers(self) -> Self:
        if len(set(self.unit_ids)) != len(self.unit_ids) or any(
            not value.int for value in self.unit_ids
        ):
            raise ValueError("physical unit IDs must be real and distinct")
        return self


class StockInput(Contract):
    version: Literal[1] = 1
    action: StockAction
    stock_date: dt.date = Field(ge=dt.date(1000, 1, 1))
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    opening_mode: Literal["COMBINED", "LINKED_GL"] | None = None
    opening_control_id: uuid.UUID | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    lines: tuple[StockLine, ...] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3 or any(ord(character) < 32 for character in value):
            raise ValueError("stock evidence needs a printable meaningful reason")
        return value

    @model_validator(mode="after")
    def shape(self) -> Self:
        if len({line.line_id for line in self.lines}) != len(self.lines):
            raise ValueError("source line identities must be distinct")
        opening_keys = [line.opening.source_key for line in self.lines if line.opening]
        if len(set(opening_keys)) != len(opening_keys):
            raise ValueError("opening source/cohort keys must be distinct")
        units = [unit for line in self.lines for unit in line.unit_ids]
        if len(units) > 1000:
            raise ValueError("a stock operation supports at most one thousand physical units")
        if len(set(units)) != len(units):
            raise ValueError("a physical unit cannot occur on two source lines")
        if (self.action == "OPENING") != (self.opening_mode is not None):
            raise ValueError("an opening explicitly supplies or links its GL asset value")
        if self.opening_control_id is not None and (
            self.action != "OPENING" or not self.opening_control_id.int
        ):
            raise ValueError("opening control belongs to its real opening operation")
        for line in self.lines:
            if (self.action == "COUNT") != (line.count is not None):
                raise ValueError("only a physical count references its native observation")
            if self.action != "COUNT" and line.quantity == 0:
                raise ValueError("physical movements require a positive base quantity")
            if self.action == "COUNT" and line.unit_ids:
                raise ValueError("serial counts require a separate identity reconciliation contract")
            if line.opening is not None and line.quantity_entry is not None:
                raise ValueError("use one entered quantity representation per opening line")
            if line.opening is not None and self.action != "OPENING":
                raise ValueError("opening evidence belongs only to an opening operation")
            if (
                line.opening
                and line.opening.received_on
                and line.opening.received_on > self.stock_date
            ):
                raise ValueError("historical opening receipt cannot follow the cutover date")
            if self.action == "PURCHASE_INVOICE":
                # The bill's accepted calculation is the value: Accounting derives each line's
                # landed cost (price, charges, non-claimable GST); none is entered here.
                if line.received_value is not None or line.zero_value_reason:
                    raise ValueError("a purchase bill's stock value is its calculated landed cost")
                if line.source_movement_id is not None:
                    raise ValueError("billing a received Receipt Note is not available yet")
            inward = self.action in {"OPENING", "RECEIPT"}
            if inward != (line.received_value is not None) and self.action != "PURCHASE_INVOICE":
                raise ValueError("only opening/receipt lines supply reviewed inward value")
            if line.received_value == 0 and not line.zero_value_reason:
                raise ValueError("zero-cost inward stock requires explicit reviewed evidence")
            if line.received_value != 0 and line.zero_value_reason:
                raise ValueError("zero-value evidence applies only to an explicit zero cost")
            if self.action in {"TRANSFER", "TRANSFER_DISPATCH"}:
                if line.destination_warehouse_id is None:
                    raise ValueError("a transfer needs its destination warehouse")
                if (line.warehouse_id, line.bin_id) == (
                    line.destination_warehouse_id,
                    line.destination_bin_id,
                ):
                    raise ValueError("a transfer must change physical position")
            elif line.destination_warehouse_id or line.destination_bin_id:
                raise ValueError("only a transfer supplies a destination")
            if self.action in {
                "CUSTOMER_RETURN",
                "SUPPLIER_RETURN",
                "TRANSFER_RECEIPT",
            }:
                if line.source_movement_id is None:
                    raise ValueError("a return must claim its original physical movement")
            elif line.source_movement_id:
                raise ValueError("a source claim belongs to a linked return")
            linked = self.action == "OPENING" and self.opening_mode == "LINKED_GL"
            if linked and line.received_value != 0 and not line.opening_journal_line_id:
                raise ValueError("a valued linked opening needs its posted GL opening line")
            if linked and line.received_value == 0 and line.opening_journal_line_id is not None:
                raise ValueError("zero-cost opening stock does not claim a GL opening line")
            if not linked and line.opening_journal_line_id:
                raise ValueError("only a linked opening references an existing GL opening")
        return self
