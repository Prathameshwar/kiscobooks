"""Read-only Purchase print facts under the original interactive authority."""

import uuid

from pydantic import Field

from voucher_execution.contracts import Contract
from voucher_execution.invoice import InvoiceCalculationDetail, InvoicePreviewCommand


class PurchasePrintCommand(Contract):
    preview: InvoicePreviewCommand = Field(repr=False)
    revision_id: uuid.UUID
    require_posted: bool


class PrintLedger(Contract):
    """The ledger account behind one printed supply line or settlement tender.

    `key` is the invoice's own `line_key` (supply) or `tender_key` (settlement). `name` is None
    when this actor may not read that account's name, so the print shows a neutral label rather
    than the name or a guess.
    """

    key: uuid.UUID
    name: str | None = Field(default=None, min_length=1, max_length=200)


class PrintLine(Contract):
    """What a person reads beside one printed supply line, under this actor's rights.

    `classification_code` is the HSN (goods) or SAC (services) the line was taxed under: the
    calculation's own tax evidence for a preview, the posted supply fact for a posted bill;
    None for an untaxed line. `unit_label` is a goods line's base-unit symbol from Catalog,
    None when this actor may not read it or the line is not goods.
    """

    key: uuid.UUID
    classification_code: str | None = Field(default=None, pattern=r"^[0-9]{4,8}$")
    unit_label: str | None = Field(default=None, min_length=1, max_length=20)


class PurchasePrintFacts(Contract):
    calculation: InvoiceCalculationDetail
    supplier_name: str | None = Field(default=None, max_length=200)
    source: str = Field(pattern="^(POSTED|PREVIEW)$")
    # Accounting's journal number for a POSTED bill (numbers are allocated on posting only);
    # None for a preview, and None when this actor may not read the journal's number.
    voucher_number: str | None = Field(default=None, min_length=1, max_length=100)
    ledgers: tuple[PrintLedger, ...] = Field(default=(), max_length=400)
    lines: tuple[PrintLine, ...] = Field(default=(), max_length=200)
