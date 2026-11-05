"""Source grains, exact wire values and committed barrier identities; no owner ORM imports."""

import datetime as dt
import hashlib
import uuid
from decimal import Decimal
from typing import Any, Literal, Self

from billing_platform.exact import exact_decimal
from billing_platform.idempotency import canonical_json
from pydantic import BaseModel, Field, field_validator, model_validator

from reporting_contract.base import Contract as Contract
from reporting_contract.inventory import InventoryRecord
from reporting_contract.gst import GstJournalTaxEvidence, GstReturnRecord
from reporting_contract.gst_outward import GstOutwardRecord
from reporting_contract.invoice import INVOICE_FACT_MODELS


class Head(Contract):
    code: str
    name: str
    nature: Literal["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"]


class Group(Contract):
    code: str
    name: str
    head_id: uuid.UUID
    parent_id: uuid.UUID | None
    status: str
    system_key: str | None
    is_deemed_positive: bool
    affects_gross_profit: bool
    nett_balances: bool
    sort_order: int


class Account(Contract):
    code: str
    name: str
    group_id: uuid.UUID
    kind: str
    party_id: uuid.UUID | None
    party_role: str | None
    currency_mode: str
    currency: str | None
    status: str
    system_key: str | None


class Party(Contract):
    code: str
    name: str
    party_type: str
    status: str


class Transition(Contract):
    period_id: uuid.UUID
    from_status: str
    to_status: str
    reason: str
    created_at: dt.datetime


class Finance(Contract):
    base_currency: str
    books_begin_date: dt.date
    fiscal_year_start_month: int
    fiscal_year_start_day: int
    configuration_hash: str
    first_posted_at: dt.datetime | None


class Period(Contract):
    fiscal_year_id: uuid.UUID
    sequence: int
    code: str
    start_date: dt.date
    end_date: dt.date
    status: str
    row_version: int


class Year(Contract):
    code: str
    start_date: dt.date
    end_date: dt.date


class Journal(Contract):
    description: str
    kind: str
    status: str
    document_date: dt.date
    posting_date: dt.date
    base_currency: str
    total_debit: str
    total_credit: str
    source_system: str
    source_type: str
    source_id: str
    source_hash: str
    number: str | None
    fiscal_period_id: uuid.UUID | None
    reversal_of_id: uuid.UUID | None
    configuration_hash: str
    posted_at: dt.datetime | None


class Line(Contract):
    description: str | None = None
    journal_id: uuid.UUID
    sequence: int
    account_id: uuid.UUID
    side: Literal["DEBIT", "CREDIT"]
    currency: str
    amount: str
    exchange_rate: str
    base_currency: str
    base_amount: str
    party_id: uuid.UUID | None
    role: str | None
    component: Literal["PRINCIPAL", "FX"]

    @field_validator("amount", "base_amount")
    @classmethod
    def exact(cls, value: str) -> str:
        number = exact_decimal(value)
        if number < 0:
            raise ValueError("non-negative amount required")
        return format(number, "f")

    @model_validator(mode="after")
    def native_amounts(self) -> Self:
        amount = Decimal(self.amount)
        base = Decimal(self.base_amount)
        rate = Decimal(self.exchange_rate)
        if (
            not rate.is_finite()
            or rate <= 0
            or rate > Decimal("99999999999.99999999")
            or rate != rate.quantize(Decimal("0.00000001"))
            or base <= 0
        ):
            raise ValueError("invalid native base amount or exchange rate")
        if (self.component == "PRINCIPAL" and amount <= 0) or (
            self.component == "FX" and (amount != 0 or self.party_id is None)
        ):
            raise ValueError("component amount differs from native journal rules")
        if (self.party_id is None and self.role is not None) or (
            self.party_id is not None and self.role not in {"CUSTOMER", "SUPPLIER"}
        ):
            raise ValueError("invalid party role")
        return self


class OpeningYtdAmount(Contract):
    account_id: uuid.UUID
    side: Literal["DEBIT", "CREDIT"]
    currency: str
    amount: str
    base_amount: str

    @field_validator("amount", "base_amount")
    @classmethod
    def positive_money(cls, value: str) -> str:
        if exact_decimal(value) <= 0:
            raise ValueError("imported YTD amounts must be positive exact money")
        return value


class OpeningCoverage(Contract):
    mode: Literal["POST_CUTOVER_ONLY", "YTD_SUMMARY"]
    posting_date: dt.date
    covered_through: dt.date
    originating_year_start: dt.date | None
    source_system: str
    source_id: str
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    ytd_summary: list[OpeningYtdAmount] | None = Field(max_length=10000)

    @model_validator(mode="after")
    def coherent_coverage(self) -> Self:
        if self.covered_through > self.posting_date:
            raise ValueError("opening coverage cannot follow cutover")
        if self.mode == "YTD_SUMMARY":
            if (
                self.originating_year_start is None
                or self.ytd_summary is None
                or not self.originating_year_start <= self.covered_through < self.posting_date
            ):
                raise ValueError("YTD coverage requires dated explicit nominal provenance")
            if (self.posting_date - self.covered_through).days != 1:
                raise ValueError("YTD coverage cannot contain a gap before cutover")
        elif self.ytd_summary is not None:
            raise ValueError("post-cutover-only coverage cannot contain YTD activity")
        return self


class Opening(Contract):
    coverage: OpeningCoverage | None = None
    journal_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)
    status: str
    posting_date: dt.date
    journal_id: uuid.UUID | None
    replacement_of_id: uuid.UUID | None
    finalized_at: dt.datetime | None


class Source(Contract):
    journal_id: uuid.UUID
    account_id: uuid.UUID
    party_id: uuid.UUID
    role: str
    status: str
    kind: str
    direction: str
    currency: str
    amount: str
    posting_date: dt.date
    reference: str


class Item(Contract):
    journal_line_id: uuid.UUID
    sequence: int
    account_id: uuid.UUID
    party_id: uuid.UUID
    role: str
    direction: str
    reference: str
    currency: str
    amount: str
    base_currency: str
    base_amount: str
    document_date: dt.date | None
    posting_date: dt.date
    due_date: dt.date | None
    terms: dict[str, Any]
    reversal_journal_id: uuid.UUID | None
    reversal_date: dt.date | None


class Allocation(Contract):
    debt_item_id: uuid.UUID
    credit_item_id: uuid.UUID
    posting_date: dt.date
    currency: str
    amount: str
    base_currency: str
    debt_base_amount: str
    credit_base_amount: str
    fx_journal_id: uuid.UUID | None
    reversal_date: dt.date | None
    fx_reversal_id: uuid.UUID | None


class Execution(Contract):
    voucher_id: uuid.UUID
    revision_id: uuid.UUID
    execution_id: uuid.UUID
    request_hash: str
    result: dict[str, Any]
    kind: str | None = None
    profile: str | None = None
    purpose: str | None = None
    type_revision_id: uuid.UUID | None = None
    class_id: uuid.UUID | None = None
    configuration_hash: str | None = None
    reversal_of_execution_id: uuid.UUID | None = None


class MoneyIntent(Contract):
    execution_id: uuid.UUID
    voucher_id: uuid.UUID
    journal_id: uuid.UUID | None
    kind: str
    status: str
    posting_date: dt.date


class BankInstrument(Contract):
    intent_id: uuid.UUID | None
    journal_line_id: uuid.UUID
    account_id: uuid.UUID
    tender_key: uuid.UUID
    mode: str
    reference: str | None
    instrument_date: dt.date | None
    booking_date: dt.date
    recognition: str
    currency: str
    amount: str


class BankEvent(Contract):
    instrument_id: uuid.UUID
    action: str
    event_date: dt.date
    reference: str | None
    reason: str


class BankStatementImport(Contract):
    account_id: uuid.UUID
    mapping_id: uuid.UUID
    file_sha256: str
    currency: str
    period_from: dt.date
    period_to: dt.date
    opening_balance: str
    closing_balance: str
    row_count: int
    status: str


class BankStatementEntry(Contract):
    import_id: uuid.UUID
    account_id: uuid.UUID
    line_number: int
    transaction_date: dt.date
    side: Literal["DEBIT", "CREDIT"]
    amount: str
    currency: str
    transaction_id: str | None
    row_sha256: str
    review_status: str
    running_balance: str | None


class BankMatch(Contract):
    statement_entry_id: uuid.UUID
    instrument_id: uuid.UUID
    amount: str
    bank_date: dt.date
    group_id: uuid.UUID
    reverses_id: uuid.UUID | None


class BankOpeningItem(Contract):
    account_id: uuid.UUID
    instrument_id: uuid.UUID
    cutoff_date: dt.date
    amount: str
    currency: str


class BankSession(Contract):
    account_id: uuid.UUID
    currency: str
    period_from: dt.date
    period_to: dt.date
    generation: int
    opening_balance: str
    closing_balance: str
    status: str
    snapshot: dict[str, Any]


class BankAdjustmentProposal(Contract):
    statement_entry_id: uuid.UUID
    account_id: uuid.UUID
    kind: str
    amount: str
    currency: str
    status: str
    voucher_id: uuid.UUID | None


class MoneyAllocation(Contract):
    intent_id: uuid.UUID
    allocation_id: uuid.UUID
    allocation_key: uuid.UUID


FACT_MODELS: dict[str, type[BaseModel]] = {
    **INVOICE_FACT_MODELS,
    "voucher_money_intent": MoneyIntent,
    "bank_instrument": BankInstrument,
    "bank_instrument_event": BankEvent,
    "bank_statement_import": BankStatementImport,
    "bank_statement_entry": BankStatementEntry,
    "bank_match_event": BankMatch,
    "bank_opening_item": BankOpeningItem,
    "bank_reconciliation_session": BankSession,
    "bank_adjustment_proposal": BankAdjustmentProposal,
    "voucher_money_allocation": MoneyAllocation,
    "party": Party,
    "fiscal_status_transition": Transition,
    "account_head": Head,
    "account_group": Group,
    "account": Account,
    "financial_setup": Finance,
    "fiscal_year": Year,
    "fiscal_period": Period,
    "journal": Journal,
    "journal_line": Line,
    "opening_batch": Opening,
    "source_document": Source,
    "open_item": Item,
    "allocation": Allocation,
    "voucher_execution": Execution,
}
SCHEMA_HASH = hashlib.sha256(
    canonical_json({key: model.model_json_schema() for key, model in sorted(FACT_MODELS.items())})
).hexdigest()
OPENING_NO_INVENTORY_SCHEMA_HASH = SCHEMA_HASH
LEGACY_SCHEMA_HASH = "847c81a317188828f3715ce306c069593debb4c539d520cb0d94a6573e499c4e"
PRE_OPENING_SCHEMA_HASH = "9001f7691b18e853ffd43b1ea80973e4690a54fbf2c5d2d5d19e4e02a03c37a6"
# Reporting-contract 0.6.0 inventory evidence remains readable without cost detail.
INVENTORY_V1_SCHEMA_HASH = "dbd648d19d503873fe15bd7b739c4a726d9f5843f262c600e31fa264f54cbd5c"
# Reporting-contract 0.8.0 predates native freshness, capture time and eligibility.
# Its committed facts validate against the additive defaults in the new models.
INVENTORY_V2_SCHEMA_HASH = "0b4102b8f825729efa319038fc30b53cb0156f3ed8783b90c32b2acda6654988"
# First native complete cuts used the original narrower unit-code bound.
NATIVE_INVENTORY_SCHEMA_HASH = "41b82e465f9915cb3f4eb9ec7587d385db4194fd2dc9d00637a71e50a5a913e6"
NATIVE_UNIT_SCHEMA_HASH = "5f19751054fd02aad737ea9c7b23de005dcb4d66461100556400cba44054864b"
# Reporting-contract 0.9.0 complete native cuts predate replenishment definitions.
NATIVE_COMPLETE_SCHEMA_HASH = "062c58aae7d9da22d70131fcdf8cdcebc54c6263a6f484ab3f438ebca656371a"

FACT_MODELS["inventory_report_record"] = InventoryRecord
SCHEMA_HASH = hashlib.sha256(
    canonical_json({key: model.model_json_schema() for key, model in sorted(FACT_MODELS.items())})
).hexdigest()
PRE_GST_SCHEMA_HASH = SCHEMA_HASH
FACT_MODELS["gst_return_record"] = GstReturnRecord
FACT_MODELS["journal_tax"] = GstJournalTaxEvidence
SCHEMA_HASH = hashlib.sha256(
    canonical_json({key: model.model_json_schema() for key, model in sorted(FACT_MODELS.items())})
).hexdigest()


PRE_GSTR1_SCHEMA_HASH = SCHEMA_HASH
FACT_MODELS["gst_outward_record"] = GstOutwardRecord
SCHEMA_HASH = hashlib.sha256(
    canonical_json({key: model.model_json_schema() for key, model in sorted(FACT_MODELS.items())})
).hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class Fact(Contract):
    entity: str
    source_id: uuid.UUID
    data: dict[str, Any] | None
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_fact(self) -> Self:
        schema = FACT_MODELS.get(self.entity)
        if schema is None:
            raise ValueError("unsupported source grain")
        if self.data is not None:
            schema.model_validate(self.data)
        if (
            digest(
                {
                    "entity": self.entity,
                    "source_id": str(self.source_id),
                    "data": self.data,
                }
            )
            != self.content_hash
        ):
            raise ValueError("source content hash mismatch")
        return self


class Control(Contract):
    counts: dict[str, int]
    base_totals: dict[str, dict[Literal["DEBIT", "CREDIT"], str]]
    coverage_start: dt.date | None
    coverage_kind: Literal["RETAINED_LEDGER", "INCOMPLETE"]


class Manifest(Contract):
    version: Literal[1] = 1
    owner: Literal["accounting"] = "accounting"
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    id: uuid.UUID
    kind: Literal["SNAPSHOT", "CHANGE"]
    sequence: int = Field(ge=0)
    generation: int = Field(ge=1)
    schema_hash: str = SCHEMA_HASH

    @field_validator("schema_hash")
    @classmethod
    def supported_schema(cls, value: str) -> str:
        # Optional analytics linkage fields do not invalidate retained source cuts.
        # Preserve the actual pre-0.13 hashes rather than recomputing old identities
        # from today's expanded Pydantic models.
        retained_analytics_schemas = {
            "24b679443e46110541f2319b3190a291b179ea7452193db2364b6d95b783df2a",
            "847c81a317188828f3715ce306c069593debb4c539d520cb0d94a6573e499c4e",
            "dbd648d19d503873fe15bd7b739c4a726d9f5843f262c600e31fa264f54cbd5c",
            "0b4102b8f825729efa319038fc30b53cb0156f3ed8783b90c32b2acda6654988",
            "41b82e465f9915cb3f4eb9ec7587d385db4194fd2dc9d00637a71e50a5a913e6",
            "5f19751054fd02aad737ea9c7b23de005dcb4d66461100556400cba44054864b",
            "062c58aae7d9da22d70131fcdf8cdcebc54c6263a6f484ab3f438ebca656371a",
            "9001f7691b18e853ffd43b1ea80973e4690a54fbf2c5d2d5d19e4e02a03c37a6",
            "717261541dea2a0062996d9229604974fb2e4cc704d42ea9f8bc3cc7691574a6",
            "14c7214f6a6a3c9f999bb2588a1f65656d9112247bc6e52768274eccc8526778",
            "d02efe7ab19f594ceaa92412f936adcde1a875ceee26d878266d9bd5c96b9710",
        }
        if value not in retained_analytics_schemas | {
            SCHEMA_HASH,
            LEGACY_SCHEMA_HASH,
            INVENTORY_V1_SCHEMA_HASH,
            INVENTORY_V2_SCHEMA_HASH,
            NATIVE_INVENTORY_SCHEMA_HASH,
            NATIVE_UNIT_SCHEMA_HASH,
            NATIVE_COMPLETE_SCHEMA_HASH,
            PRE_OPENING_SCHEMA_HASH,
            OPENING_NO_INVENTORY_SCHEMA_HASH,
            PRE_GST_SCHEMA_HASH,
            PRE_GSTR1_SCHEMA_HASH,
        }:
            raise ValueError("unsupported financial feed schema")
        return value

    scope_hash: str
    permission_hash: str
    fact_count: int = Field(ge=0)
    facts_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    control: Control

    @model_validator(mode="after")
    def legacy_grains(self) -> Self:
        if self.schema_hash in {LEGACY_SCHEMA_HASH, "847c81a317188828f3715ce306c069593debb4c539d520cb0d94a6573e499c4e"} and self.control.counts.get(
            "inventory_report_record", 0
        ):
            raise ValueError("legacy financial schema cannot carry stock facts")
        return self


class FactPage(Contract):
    manifest_id: uuid.UUID
    items: list[Fact] = Field(max_length=200)
    next_after: int | None = Field(default=None, ge=1)


class HeadBarrier(Contract):
    sequence: int = Field(ge=0)
    manifest: Manifest | None
