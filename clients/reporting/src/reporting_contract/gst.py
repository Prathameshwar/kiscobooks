"""Immutable GST return allocations owned by Accounting."""

import datetime as dt
import uuid
from decimal import Decimal, InvalidOperation
from typing import Literal, Self
from typing import Any

from pydantic import Field, field_validator, model_validator

from reporting_contract.base import Contract

CATEGORIES = frozenset(
    {
        "3.1a",
        "3.1b",
        "3.1c",
        "3.1d",
        "3.1e",
        "3.1.1i",
        "3.1.1ii",
        "3.2",
        "INWARD_TAXABLE",
        "INWARD_INELIGIBLE",
        "4A1",
        "4A2",
        "4A3",
        "4A4",
        "4A5",
        "4B1",
        "4B2",
        "4D1",
        "4D2",
        "5_EXEMPT_INTER",
        "5_EXEMPT_INTRA",
        "5_NONGST_INTER",
        "5_NONGST_INTRA",
        "INTEREST",
        "LATE_FEE",
        "OPENING_ITC",
        "OPENING_CASH",
        "CASH_DEPOSIT",
        "OFFSET_NORMAL_CASH",
        "OFFSET_RCM_CASH",
        "OFFSET_ECO_CASH",
        "OFFSET_INTEREST_CASH",
        "OFFSET_LATE_FEE_CASH",
        "OFFSET_NORMAL_ITC",
        "OFFSET_RCM_ITC",
        "OFFSET_ECO_ITC",
        "PRIOR_LIABILITY",
        "COVERAGE",
        "GSTR1",
        "GSTR2B",
        "IMS",
        "PREVIOUS_RETURN",
    }
)
COVERAGE_AREAS = frozenset(
    {"OUTWARD", "INWARD", "ITC", "PAYMENT", "OPENING", "GSTR1", "GSTR2B", "IMS"}
)


class GstReturnRecord(Contract):
    registration_id: uuid.UUID
    return_date: dt.date
    event_date: dt.date
    category: str = Field(max_length=32, json_schema_extra={"enum": sorted(CATEGORIES)})
    source_entity: Literal[
        "invoice_supply_fact", "invoice_credit_action", "journal", "EXTERNAL"
    ]
    source_id: uuid.UUID | None = None
    original_record_id: uuid.UUID | None = None
    reference: str = Field(min_length=1, max_length=120)
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    currency: Literal["INR"] = "INR"
    conversion_rate: str | None = None
    taxable: str = "0.0000"
    igst: str = "0.0000"
    cgst: str = "0.0000"
    sgst: str = "0.0000"
    cess: str = "0.0000"
    place_of_supply: str | None = Field(default=None, pattern=r"^[0-9]{2}$")
    recipient: Literal["UNREGISTERED", "COMPOSITION", "UIN"] | None = None
    is_advance: bool = False
    credit_head: Literal["IGST", "CGST", "SGST", "CESS"] | None = None
    coverage_area: str | None = Field(default=None, max_length=20)
    coverage_status: Literal["COMPLETE", "NOT_APPLICABLE"] | None = None
    covered_sequence: int | None = Field(default=None, ge=0)
    explanation: str = Field(default="", max_length=1000)

    @field_validator("conversion_rate", mode="before")
    @classmethod
    def exact_conversion(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("conversion rate requires an exact retained rate")
        try:
            rate = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("invalid conversion rate") from exc
        if (
            not rate.is_finite()
            or rate <= 0
            or rate >= Decimal("100000000000")
            or rate.quantize(Decimal("0.00000001")) != rate
        ):
            raise ValueError("conversion rate exceeds DECIMAL(19,8)")
        return format(rate, ".8f")

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError("unknown statutory allocation category")
        return value

    @field_validator("taxable", "igst", "cgst", "sgst", "cess", mode="before")
    @classmethod
    def exact_amount(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("GST money must be an exact decimal string")
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("enter a valid exact GST amount") from exc
        if (
            not amount.is_finite()
            or abs(amount) >= Decimal("1000000000000000")
            or amount.quantize(Decimal("0.0001")) != amount
        ):
            raise ValueError("GST money exceeds DECIMAL(19,4)")
        return format(amount, ".4f")

    @model_validator(mode="after")
    def lineage(self) -> Self:
        if self.category.startswith("OFFSET_") or self.category in {
            "INTEREST",
            "LATE_FEE",
            "OPENING_ITC",
            "OPENING_CASH",
            "CASH_DEPOSIT",
        }:
            if any(
                Decimal(getattr(self, head)) < 0
                for head in ("taxable", "igst", "cgst", "sgst", "cess")
            ):
                raise ValueError(
                    "payment, opening and fee allocations cannot be negative"
                )
        if self.source_entity != "EXTERNAL" and self.source_id is None:
            raise ValueError("native evidence requires its source identity")
        if self.category == "3.2" and (not self.place_of_supply or not self.recipient):
            raise ValueError("Table 3.2 requires state and recipient class")
        if self.category == "COVERAGE":
            if self.coverage_area not in COVERAGE_AREAS or not self.coverage_status:
                raise ValueError(
                    "coverage requires an explicit statutory area and status"
                )
            if any(
                Decimal(getattr(self, head))
                for head in ("taxable", "igst", "cgst", "sgst", "cess")
            ):
                raise ValueError("coverage cannot carry amounts")
        if self.category == "OFFSET_NORMAL_ITC" and not self.credit_head:
            raise ValueError("ITC offset requires the source credit head")
        if self.category == "4D1" and not self.original_record_id:
            raise ValueError(
                "reclaimed temporary credit requires the original reversal"
            )
        return self


class GstJournalTaxEvidence(Contract):
    journal_id: uuid.UUID
    company_registration_id: uuid.UUID | None
    direction: Literal["SALE", "PURCHASE"]
    currency: str
    taxable_value: str
    tax_total: str
    reverse_charge: bool
    snapshot_hash: str
    snapshot: dict[str, Any]

    @field_validator("taxable_value", "tax_total", mode="before")
    @classmethod
    def exact_amount(cls, value: object) -> str:
        return GstReturnRecord.exact_amount(value)
