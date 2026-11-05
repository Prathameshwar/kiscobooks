"""Bounded opening calculation, manifest and reconciliation contracts."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Literal, Self

from billing_platform.idempotency import canonical_json
from billing_platform.listing import ListQuery
from pydantic import AfterValidator, Field, model_validator
from voucher_execution.opening import OpeningCapture
from voucher_execution.stock import Exact, StockInput, StockLine

from accounting.schemas.masters import Input

OpeningReason = Annotated[
    str, Field(min_length=3, max_length=500), AfterValidator(StockInput.meaningful_reason)
]


class OpeningCalculate(Input):
    stock_date: dt.date = Field(ge=dt.date(1000, 1, 1))
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    opening: OpeningCapture
    received_value: Exact | None = Field(default=None, ge=0)


class OpeningCalculated(Input):
    company_id: uuid.UUID
    currency: str
    base_quantity: Exact
    received_value: Exact
    derived_unit_cost: str
    derived_base_unit_cost: str
    unit_revision_id: uuid.UUID
    catalog_generation: int
    source_version: int
    informational_only: Literal[True] = True


class OpeningManifest(Input):
    stock_date: dt.date = Field(ge=dt.date(1000, 1, 1))
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    opening_mode: Literal["COMBINED", "LINKED_GL"]
    lines: tuple[StockLine, ...] = Field(default=(), max_length=1000)
    reason: OpeningReason
    adopt_existing: bool = False

    @model_validator(mode="after")
    def closed_manifest(self) -> Self:
        keys = [line.opening.source_key for line in self.lines if line.opening]
        units = [unit for line in self.lines for unit in line.unit_ids]
        if len(keys) != len(self.lines) or len(set(keys)) != len(keys):
            raise ValueError("every manifest cohort needs its distinct stable opening source key")
        if len(set(units)) != len(units) or len(units) > 10_000:
            raise ValueError("manifest serials must be distinct and bounded to ten thousand")
        if len({line.line_id for line in self.lines}) != len(self.lines):
            raise ValueError("manifest line identities must be distinct")
        for line in self.lines:
            StockInput(
                action="OPENING",
                stock_date=self.stock_date,
                currency=self.currency,
                opening_mode=self.opening_mode,
                lines=(line,),
                reason=self.reason,
            )
        if sum((line.received_value or Decimal(0) for line in self.lines), Decimal(0)) > Decimal(
            "999999999999999.9999"
        ):
            raise ValueError("opening manifest total exceeds supported company carrying value")
        if self.adopt_existing and self.lines:
            raise ValueError("legacy adoption cannot invent new opening allocations")
        canonical_json(self.model_dump(mode="json"), maximum_bytes=2_097_152)
        return self


class OpeningControlDetail(Input):
    id: uuid.UUID
    company_id: uuid.UUID
    item_id: uuid.UUID | None = None
    expected_version: int
    status: Literal["OPEN", "FINALIZED"]
    books_begin_date: dt.date
    currency: str
    manifest_hash: str
    expected_cohorts: int
    applied_cohorts: int
    expected_value: Exact
    applied_value: Exact
    missing_source_keys: list[str]
    blockers: list[str]
    legacy_adopted: bool = False


class OpeningCohortQuery(ListQuery):
    item_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    include_reversed: bool = False


class OpeningRevisionItem(Input):
    id: uuid.UUID
    revision: int
    manifest_hash: str
    currency: str
    created_at: dt.datetime
    created_by: uuid.UUID


class OpeningExportTicket(Input):
    token: str
    expires_in: int
    download_path: str


class OpeningExportQuery(Input):
    token: str = Field(min_length=1, max_length=4096)


class OpeningProjectedEntry(Input):
    account_id: uuid.UUID
    side: Literal["DEBIT", "CREDIT"]
    amount: Exact


class OpeningProjectedClaim(Input):
    journal_line_id: uuid.UUID
    amount: Exact


class OpeningAccountingPreview(Input):
    company_id: uuid.UUID
    control_id: uuid.UUID
    expected_version: int
    manifest_hash: str
    currency: str
    opening_mode: Literal["COMBINED", "LINKED_GL"]
    remaining_value: Exact
    additional_gl_value: Exact
    entries: list[OpeningProjectedEntry]
    linked_claims: list[OpeningProjectedClaim]
    informational_only: Literal[True] = True


class OpeningCohort(Input):
    id: uuid.UUID
    source_key: str
    posting_id: uuid.UUID
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID | None
    lot_id: uuid.UUID | None
    quantity: Exact
    value: Exact
    currency: str
    cutover_date: dt.date
    received_on: dt.date | None
    history_known: bool
    reversed: bool


class OpeningFinalize(Input):
    expected_version: int = Field(strict=True, ge=1)
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: OpeningReason


class OpeningReplace(OpeningFinalize):
    manifest: OpeningManifest


class OpeningReadiness(Input):
    company_id: uuid.UUID
    books_begin_date: dt.date
    control_id: uuid.UUID | None
    status: Literal["NOT_STARTED", "OPEN", "FINALIZED", "LEGACY_ACTIVITY"]
    blockers: list[str]
    can_start: bool
    posting_enabled: bool
    expected_generation: int | None
    can_confirm_zero: bool = False


class OpeningCapabilities(Input):
    company_id: uuid.UUID
    posting_enabled: bool
    valuation_methods: list[Literal["FIFO", "MOVING_AVERAGE"]]
    ownership: Literal["COMPANY"] = "COMPANY"
    disposition: Literal["USABLE"] = "USABLE"
    unit_conversion: Literal["FIXED"] = "FIXED"
    maximum_cohorts: Literal[1000] = 1000
    maximum_serials: Literal[10000] = 10000
    maximum_execution_lines: Literal[100] = 100
    maximum_execution_serials: Literal[1000] = 1000
    zero_cost_requires_configuration_and_reason: Literal[True] = True


class OpeningZeroConfirm(Input):
    expected_generation: int = Field(strict=True, ge=1)
    reason: OpeningReason
