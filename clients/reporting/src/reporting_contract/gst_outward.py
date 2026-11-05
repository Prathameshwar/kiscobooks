"""Immutable detailed outward GST evidence. No posting or tax-rate engine."""

import datetime as dt
import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from reporting_contract.base import Contract
from reporting_contract.gst import GstReturnRecord

MONEY = ("taxable", "igst", "cgst", "sgst", "cess")
GSTIN = r"^[0-9]{2}[A-Z0-9]{13}$"
NUMBER = r"^[A-Za-z0-9/-]{1,16}$"
AREAS = frozenset(
    {"OUTWARD", "NOTES", "ADVANCES", "HSN", "DOCUMENTS", "ECO", "IFF", "PORTAL"}
)
DOCUMENT_KINDS = frozenset(
    {
        "INVOICE",
        "CREDIT_NOTE",
        "DEBIT_NOTE",
        "AMENDMENT",
        "ADVANCE",
        "ADVANCE_ADJUSTMENT",
        "ECO_OPERATOR",
    }
)


class OutwardItem(Contract):
    source_line_id: uuid.UUID | None = None
    description: str = Field(default="", max_length=200)
    goods_service: Literal["GOODS", "SERVICES"] = "SERVICES"
    hsn: str = Field(default="", max_length=8, pattern=r"^(?:[0-9]{4,8})?$")
    uqc: str = Field(default="", max_length=8)
    quantity: str = "0.0000"
    treatment: Literal["TAXABLE", "NIL_RATED", "EXEMPT", "NON_GST"] = "TAXABLE"
    rate: str = "0.00000000"
    taxable: str = "0.0000"
    igst: str = "0.0000"
    cgst: str = "0.0000"
    sgst: str = "0.0000"
    cess: str = "0.0000"

    @field_validator(
        "quantity", "taxable", "igst", "cgst", "sgst", "cess", mode="before"
    )
    @classmethod
    def exact(cls, value: object) -> str:
        result = GstReturnRecord.exact_amount(value)
        if Decimal(result) < 0:
            raise ValueError(
                "document detail amounts and quantities must be non-negative"
            )
        return result

    @field_validator("rate", mode="before")
    @classmethod
    def exact_rate(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("rate requires an exact decimal string")
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("invalid retained GST rate") from exc
        if (
            not result.is_finite()
            or result < 0
            or result > 100
            or result != result.quantize(Decimal("0.00000001"))
        ):
            raise ValueError("invalid retained GST rate")
        return format(result, ".8f")

    @model_validator(mode="after")
    def treatment_heads(self) -> Self:
        if self.treatment != "TAXABLE" and any(
            Decimal(getattr(self, head)) for head in MONEY[1:]
        ):
            raise ValueError("non-taxable supply details cannot contain GST")
        if self.igst != "0.0000" and (self.cgst != "0.0000" or self.sgst != "0.0000"):
            raise ValueError(
                "a supply line cannot mix integrated and central/state tax"
            )
        return self


class OutwardDetails(Contract):
    recipient_type: Literal["REGISTERED", "UNREGISTERED", "UIN"] = "UNREGISTERED"
    recipient_gstin: str | None = Field(default=None, pattern=GSTIN)
    recipient_name: str = Field(default="", max_length=200)
    place_of_supply: str | None = Field(default=None, pattern=r"^[0-9]{2}$")
    supply_type: Literal[
        "DOMESTIC",
        "EXPORT_WPAY",
        "EXPORT_WOPAY",
        "SEZ_WPAY",
        "SEZ_WOPAY",
        "DEEMED_EXPORT",
    ] = "DOMESTIC"
    reverse_charge: bool = False
    items: list[OutwardItem] = Field(default_factory=list, max_length=200)
    invoice_rounding: str = "0.0000"
    eco_scheme: Literal["TCS", "9_5"] | None = None
    operator_gstin: str | None = Field(default=None, pattern=GSTIN)
    supplier_gstin: str | None = Field(default=None, pattern=GSTIN)
    supplier_type: Literal["REGISTERED", "UNREGISTERED"] = "REGISTERED"
    shipping_bill_number: str | None = Field(default=None, max_length=40)
    shipping_bill_date: dt.date | None = None
    port_code: str | None = Field(default=None, max_length=16)
    export_reference: str | None = Field(default=None, max_length=120)
    irn: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    tax_note: bool = True
    original_filing_reference: str | None = Field(default=None, max_length=120)
    original_filing_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    annual_return_checked: bool = False
    annual_return_filed_date: dt.date | None = None
    original_supply_date: dt.date | None = None
    source_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    source_invoice_value: str | None = None
    conversion_rate: str | None = None
    conversion_date: dt.date | None = None
    conversion_reference: str | None = Field(default=None, max_length=120)
    prior_filed_channel: Literal["IFF", "GSTR1A"] | None = None
    prior_filing_reference: str | None = Field(default=None, max_length=120)
    prior_filing_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    prior_filing_date: dt.date | None = None
    document_category: str | None = Field(default=None, max_length=40)
    serial_from: str | None = Field(default=None, pattern=NUMBER)
    serial_to: str | None = Field(default=None, pattern=NUMBER)
    total_count: int = Field(default=0, strict=True, ge=0, le=1000000)
    cancelled_count: int = Field(default=0, strict=True, ge=0, le=1000000)
    coverage_area: str | None = Field(default=None, max_length=20)
    coverage_status: Literal["COMPLETE", "NOT_APPLICABLE"] | None = None
    covered_sequence: int | None = Field(default=None, ge=0)

    @field_validator("invoice_rounding", mode="before")
    @classmethod
    def exact_rounding(cls, value: object) -> str:
        return GstReturnRecord.exact_amount(value)

    @field_validator("source_invoice_value", mode="before")
    @classmethod
    def exact_source_value(cls, value: object) -> str | None:
        return None if value is None else GstReturnRecord.exact_amount(value)

    @field_validator("conversion_rate", mode="before")
    @classmethod
    def exact_conversion(cls, value: object) -> str | None:
        return GstReturnRecord.exact_conversion(value)

    @model_validator(mode="after")
    def evidence(self) -> Self:
        if self.recipient_type == "UNREGISTERED" and self.recipient_gstin is not None:
            raise ValueError("unregistered recipients cannot have a GSTIN")
        if self.recipient_type != "UNREGISTERED" and not self.recipient_gstin:
            raise ValueError(
                "registered/UIN recipients require their retained identifier"
            )
        if self.cancelled_count > self.total_count:
            raise ValueError("cancelled count exceeds issued count")
        if self.eco_scheme and not self.operator_gstin:
            raise ValueError("ECO disclosure requires an operator GSTIN")
        if self.prior_filed_channel and not all(
            (
                self.prior_filing_reference,
                self.prior_filing_hash,
                self.prior_filing_date,
            )
        ):
            raise ValueError(
                "prior IFF/GSTR-1A inclusion requires actual retained filing evidence"
            )
        conversion = (
            self.source_currency,
            self.source_invoice_value,
            self.conversion_rate,
            self.conversion_date,
            self.conversion_reference,
        )
        if any(value is not None for value in conversion) and not all(
            value is not None for value in conversion
        ):
            raise ValueError(
                "foreign source conversion requires currency, value, rate, date and retained statutory-rate evidence"
            )
        return self


class GstOutwardRecord(Contract):
    registration_id: uuid.UUID
    return_date: dt.date
    document_date: dt.date
    kind: Literal[
        "INVOICE",
        "CREDIT_NOTE",
        "DEBIT_NOTE",
        "AMENDMENT",
        "ADVANCE",
        "ADVANCE_ADJUSTMENT",
        "ECO_OPERATOR",
        "DOCUMENTS",
        "COVERAGE",
        "PORTAL",
    ]
    document_number: str = Field(default="", max_length=16)
    source_entity: Literal["invoice_record", "EXTERNAL"]
    source_id: uuid.UUID | None = None
    original_record_id: uuid.UUID | None = None
    reference: str = Field(min_length=1, max_length=120)
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    explanation: str = Field(min_length=1, max_length=1000)
    currency: Literal["INR"] = "INR"
    invoice_value: str = "0.0000"
    taxable: str = "0.0000"
    igst: str = "0.0000"
    cgst: str = "0.0000"
    sgst: str = "0.0000"
    cess: str = "0.0000"
    details: OutwardDetails = Field(default_factory=OutwardDetails)

    @field_validator(
        "invoice_value", "taxable", "igst", "cgst", "sgst", "cess", mode="before"
    )
    @classmethod
    def exact(cls, value: object) -> str:
        return GstReturnRecord.exact_amount(value)

    @model_validator(mode="before")
    @classmethod
    def line_totals(cls, value: Any) -> Any:
        if not isinstance(value, dict) or value.get("kind") not in DOCUMENT_KINDS:
            return value
        details = OutwardDetails.model_validate(value.get("details", {}))
        values = dict(value)
        for head in MONEY:
            total = sum(
                (Decimal(getattr(item, head)) for item in details.items), Decimal(0)
            )
            if (
                head in values
                and Decimal(GstReturnRecord.exact_amount(values[head])) != total
            ):
                raise ValueError("document totals do not match retained line details")
            values[head] = format(total, ".4f")
        return values

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.source_entity == "invoice_record" and not self.source_id:
            raise ValueError("native document identity is required")
        if self.kind in DOCUMENT_KINDS:
            import re

            if not re.fullmatch(NUMBER, self.document_number) or not self.details.items:
                raise ValueError(
                    "supply evidence requires a statutory document number and line details"
                )
            if not self.details.place_of_supply:
                raise ValueError("supply evidence requires place of supply")
            total = sum((Decimal(getattr(self, head)) for head in MONEY), Decimal(0))
            if Decimal(self.invoice_value) != total + Decimal(
                self.details.invoice_rounding
            ):
                raise ValueError(
                    "invoice value must match its retained basis, taxes and rounding"
                )
            if (
                self.details.source_invoice_value is not None
                and self.details.conversion_rate is not None
            ):
                product = Decimal(self.details.source_invoice_value) * Decimal(
                    self.details.conversion_rate
                )
                if abs(product) >= Decimal("1000000000000000"):
                    raise ValueError("converted invoice value exceeds DECIMAL(19,4)")
                converted = product.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                if converted != Decimal(self.invoice_value):
                    raise ValueError(
                        "retained conversion must match the INR invoice value"
                    )
            if (
                self.details.supply_type.startswith("SEZ")
                and self.details.recipient_type != "REGISTERED"
            ):
                raise ValueError("SEZ supplies require a registered recipient")
            if (
                self.details.supply_type.startswith("EXPORT")
                and self.details.recipient_type != "UNREGISTERED"
            ):
                raise ValueError("exports use an unregistered overseas recipient")
            if (
                self.kind == "ECO_OPERATOR"
                and self.details.supplier_type == "REGISTERED"
                and not self.details.supplier_gstin
            ):
                raise ValueError("ECO registered supplier evidence requires its GSTIN")
        elif self.details.items:
            raise ValueError(
                "coverage, document series and portal comparisons have no invoice lines"
            )
        if self.kind == "COVERAGE":
            if (
                self.details.coverage_area not in AREAS
                or not self.details.coverage_status
            ):
                raise ValueError(
                    "coverage requires an explicit area and completeness status"
                )
            if any(Decimal(getattr(self, head)) for head in MONEY) or Decimal(
                self.invoice_value
            ):
                raise ValueError("coverage cannot carry monetary amounts")
        if self.kind == "DOCUMENTS" and not all(
            (
                self.details.document_category,
                self.details.serial_from,
                self.details.serial_to,
            )
        ):
            raise ValueError(
                "document series requires its category and actual serial range"
            )
        if self.kind == "DOCUMENTS" and (
            any(Decimal(getattr(self, head)) for head in MONEY)
            or Decimal(self.invoice_value)
        ):
            raise ValueError("document series cannot carry monetary amounts")
        if self.kind == "AMENDMENT" and not all(
            (
                self.original_record_id,
                self.details.original_filing_reference,
                self.details.original_filing_hash,
                self.details.annual_return_checked,
            )
        ):
            raise ValueError(
                "amendment requires its original document and reviewed original filing/annual-return evidence"
            )
        return self
