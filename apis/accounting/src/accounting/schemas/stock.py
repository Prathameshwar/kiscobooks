"""Stock account configuration and lean, field-protected physical evidence."""

import datetime as dt
import uuid
from typing import Literal

from billing_platform.listing import ListQuery
from pydantic import Field

from accounting.schemas.masters import DecimalInput, Detail, Input


class StockAccountPolicyCreate(Input):
    expected_generation: int = Field(strict=True, ge=1)
    correct_unused_id: uuid.UUID | None = None
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))
    inventory_account_id: uuid.UUID
    receipt_clearing_account_id: uuid.UUID
    dispatch_clearing_account_id: uuid.UUID
    opening_offset_account_id: uuid.UUID
    variance_account_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=500)


class StockAccountPolicyDetail(Detail):
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    inventory_account_id: uuid.UUID | None = None
    receipt_clearing_account_id: uuid.UUID | None = None
    dispatch_clearing_account_id: uuid.UUID | None = None
    opening_offset_account_id: uuid.UUID | None = None
    variance_account_id: uuid.UUID | None = None
    reason: str | None = None


class StockPostingDetail(Detail):
    action: str | None = None
    stock_date: dt.date | None = None
    posting_date: dt.date | None = None
    currency: str | None = None
    voucher_id: uuid.UUID | None = None
    revision_id: uuid.UUID | None = None
    execution_id: uuid.UUID | None = None
    journal_id: uuid.UUID | None = None
    reverses_id: uuid.UUID | None = None


class StockMovementDetail(Detail):
    stock_date: dt.date | None = None
    posting_date: dt.date | None = None
    currency: str | None = None
    posting_id: uuid.UUID | None = None
    line_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    bin_id: uuid.UUID | None = None
    lot_id: uuid.UUID | None = None
    quantity: DecimalInput | None = None
    value: DecimalInput | None = None
    source_movement_id: uuid.UUID | None = None


class StockPositionDetail(Detail):
    item_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    bin_id: uuid.UUID | None = None
    lot_id: uuid.UUID | None = None
    custody_kind: str | None = None
    quantity: DecimalInput | None = None


class StockQuery(ListQuery):
    item_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    bin_id: uuid.UUID | None = None
    lot_id: uuid.UUID | None = None
    posting_id: uuid.UUID | None = None
    voucher_id: uuid.UUID | None = None


class StockPositionListItem(Input):
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    bin_id: uuid.UUID | None = None
    lot_id: uuid.UUID | None = None
    custody_kind: str | None = None
    quantity: DecimalInput | None = None


class StockMovementListItem(StockPositionListItem):
    posting_id: uuid.UUID | None = None
    line_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    value: DecimalInput | None = None
    currency: str | None = None
    stock_date: dt.date | None = None
    posting_date: dt.date | None = None
    source_movement_id: uuid.UUID | None = None


class StockPostingListItem(Input):
    id: uuid.UUID
    row_version: int | None = None
    action: str | None = None
    stock_date: dt.date | None = None
    posting_date: dt.date | None = None
    currency: str | None = None
    voucher_id: uuid.UUID | None = None
    journal_id: uuid.UUID | None = None
    reverses_id: uuid.UUID | None = None


class StockAccountPolicyListItem(Input):
    id: uuid.UUID
    row_version: int | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class StockConfiguration(Input):
    generation: int
    posting_enabled: bool
    can_configure: bool
    correctable_policy_id: uuid.UUID | None = None


class StockCostPoolListItem(Input):
    id: uuid.UUID
    row_version: int | None = None
    item_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    method: str | None = None
    quantity: DecimalInput | None = None
    value: DecimalInput | None = None
    currency: str | None = None
    last_stock_date: dt.date | None = None


class StockCostPoolDetail(StockCostPoolListItem):
    company_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class StockSelectionInput(Input):
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    stock_date: dt.date = Field(ge=dt.date(1000, 1, 1))
    operation: Literal["SALE_ISSUE", "TRANSFER_OUT", "SUPPLIER_RETURN_ISSUE"] = "SALE_ISSUE"


class StockSelectionItem(Input):
    position_id: uuid.UUID
    origin_id: uuid.UUID
    quantity: DecimalInput
    lot_id: uuid.UUID | None
    bin_id: uuid.UUID | None
    received_on: dt.date
    expires_on: dt.date | None
    history_known: bool = True


class StockSelection(Input):
    company_id: uuid.UUID
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    stock_date: dt.date
    issue_strategy: Literal["FIFO", "FEFO"]
    items: list[StockSelectionItem]
    has_more: bool


class StockAvailableUnitQuery(ListQuery):
    position_id: uuid.UUID
    stock_date: dt.date = Field(ge=dt.date(1000, 1, 1))
    operation: Literal["SALE_ISSUE", "TRANSFER_OUT", "SUPPLIER_RETURN_ISSUE"] = "SALE_ISSUE"


class StockOpeningLineQuery(ListQuery):
    stock_date: dt.date = Field(ge=dt.date(1000, 1, 1))


class StockOpeningLineListItem(Input):
    id: uuid.UUID
    journal_id: uuid.UUID
    number: str
    currency: str
    remaining_value: DecimalInput
