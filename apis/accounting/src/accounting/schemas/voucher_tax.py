"""Tax blocks a journal or party document may carry (tax-accounting Phase 8).

Kept free of ledger imports: ``JournalCreate`` and ``SourceCreate`` embed these blocks, and the
preview and evidence contracts that reference those requests live in ``schemas.tax_analysis``.
"""

import datetime as dt
import uuid
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, model_validator

from accounting.schemas.masters import DecimalInput, Detail, Input


def _exact(value: Any) -> Any:
    if isinstance(value, float | bool):
        raise ValueError("financial amounts require exact decimal strings")
    return value


TaxableValue = Annotated[
    DecimalInput,
    BeforeValidator(_exact),
    Field(gt=0, max_digits=19, decimal_places=4, allow_inf_nan=False),
]
#: ``IN-MH`` or ``MH``; the country prefix is optional and compared by its state part.
StateCode = Annotated[str, Field(pattern=r"^([A-Z]{2}-)?[A-Z0-9]{1,3}$")]


class TaxParty(Input):
    """Counterparty and supply facts shared by journals and party documents."""

    party_registration_id: uuid.UUID | None = None
    #: The counterparty's state when it has no registration (an unregistered party).
    party_state: StateCode | None = None
    #: Defaults to the company's single supplier-class GST registration on the posting date.
    company_registration_id: uuid.UUID | None = None
    place_of_supply: StateCode | None = None
    zero_rated_with_payment: bool = False


class VoucherTax(TaxParty):
    """GST on a manual journal; lines on accounts with a tax default are the taxable lines."""

    direction: Literal["SALE", "PURCHASE"]
    party_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def party_for_registration(self) -> "VoucherTax":
        if self.party_registration_id is not None and self.party_id is None:
            raise ValueError("a party registration requires its party")
        return self


class SourceTax(TaxParty):
    """GST and TDS/TCS on an INVOICE, BILL or PAYMENT; the party is the document's party."""

    #: Value before GST on the counterpart line (INVOICE and BILL).
    taxable_value: TaxableValue | None = None
    gst: bool = True
    withholding_section_id: uuid.UUID | None = None


def validate_source_tax(kind: str, tax: SourceTax | None) -> None:
    if tax is None:
        return
    if kind not in {"INVOICE", "BILL", "PAYMENT"}:
        raise ValueError("only invoices, bills and payments carry tax")
    if kind == "PAYMENT":
        if tax.gst or tax.withholding_section_id is None or tax.taxable_value is not None:
            raise ValueError("payment tax is withholding only: gst false and a section")
        return
    if tax.taxable_value is None:
        raise ValueError("invoice and bill tax requires taxable_value")
    if not tax.gst and tax.withholding_section_id is None:
        raise ValueError("tax without GST requires a withholding section")


class JournalTaxDetail(Detail):
    journal_id: uuid.UUID | None = None
    direction: Literal["SALE", "PURCHASE"] | None = None
    party_id: uuid.UUID | None = None
    company_registration_id: uuid.UUID | None = None
    party_registration_id: uuid.UUID | None = None
    place_of_supply: str | None = None
    supply_context: str | None = None
    supply_reason: str | None = None
    reverse_charge: bool | None = None
    currency: str | None = None
    taxable_value: DecimalInput | None = None
    tax_total: DecimalInput | None = None
    withholding_kind: Literal["TDS", "TCS"] | None = None
    withholding_section_id: uuid.UUID | None = None
    withholding_amount: DecimalInput | None = None
    withholding_base: DecimalInput | None = None
    withholding_tax: DecimalInput | None = None
    certificate_id: uuid.UUID | None = None
    certificate_base: DecimalInput | None = None
    line_count: int | None = None
    request: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None
    snapshot_hash: str | None = None


class JournalTaxListItem(Detail):
    journal_id: uuid.UUID | None = None
    direction: Literal["SALE", "PURCHASE"] | None = None
    party_id: uuid.UUID | None = None
    supply_context: str | None = None
    reverse_charge: bool | None = None
    currency: str | None = None
    taxable_value: DecimalInput | None = None
    tax_total: DecimalInput | None = None
    withholding_kind: Literal["TDS", "TCS"] | None = None
    withholding_tax: DecimalInput | None = None


TaxStatus = Literal["READY", "EXCEPTION"]


class TaxExceptionItem(Input):
    code: str
    message: str
    line: int | None = None


class TaxPreviewLine(Input):
    sequence: int
    account_id: uuid.UUID
    side: Literal["DEBIT", "CREDIT"]
    currency: str
    amount: DecimalInput
    generated: bool
    purpose: str | None = None


class TaxPreview(Input):
    """The read-only *Tax Analysis* of a voucher as it would be drafted now."""

    status: TaxStatus
    exceptions: list[TaxExceptionItem]
    posting_date: dt.date
    direction: Literal["SALE", "PURCHASE"]
    currency: str
    taxable_value: DecimalInput
    tax_total: DecimalInput
    withholding_kind: Literal["TDS", "TCS"] | None = None
    withholding_tax: DecimalInput | None = None
    party_amount: DecimalInput | None = None
    analysis: dict[str, Any] | None = None
    lines: list[TaxPreviewLine]
