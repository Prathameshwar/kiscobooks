"""Foundation payloads deliberately reject unimplemented monetary/effect sections."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from billing_platform.exact import exact_decimal
from billing_platform.idempotency import canonical_json
from pydantic import (
    BeforeValidator,
    Field,
    SerializerFunctionWrapHandler,
    StrictBool,
    WithJsonSchema,
    model_serializer,
    model_validator,
)
from voucher_execution.invoice import InvoiceInput
from voucher_execution.money import MoneyInput
from voucher_execution.stock import StockInput

from vouchers.schemas.configuration import Contract, Version

Quantity = Annotated[
    Decimal,
    BeforeValidator(exact_decimal),
    WithJsonSchema({"type": "string"}, mode="validation"),
    Field(ge=0, max_digits=19, decimal_places=4, allow_inf_nan=False),
]


class ItemInput(Contract):
    item_id: uuid.UUID
    item_version: int = Field(strict=True, ge=1)
    unit_id: uuid.UUID
    actual_quantity: Quantity
    billed_quantity: Quantity
    planned_quantity: Quantity | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @model_serializer(mode="wrap")
    def stable_legacy_item(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.planned_quantity is None:
            result.pop("planned_quantity", None)
        return result


class LineInput(Contract):
    line_key: uuid.UUID
    line_kind: Literal["ITEM"] = "ITEM"
    description: str = Field(default="", max_length=1000)
    item: ItemInput


class PartyInput(Contract):
    role: Literal["CUSTOMER", "SUPPLIER", "CONSIGNEE", "PRINCIPAL", "WORKER", "CARRIER", "OTHER"]
    party_id: uuid.UUID
    source_version: int = Field(strict=True, ge=1)


class ReferenceInput(Contract):
    purpose: Literal["SUPPLIER_INVOICE", "CUSTOMER_ORDER", "EXTERNAL", "CHALLAN"]
    reference: str = Field(min_length=1, max_length=120)
    reference_date: dt.date | None = None


class AttachmentInput(Contract):
    object_key: str = Field(pattern=r"^[a-zA-Z0-9/_-]{1,200}$")
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: Literal["application/pdf", "image/png", "image/jpeg", "text/plain"]
    size_bytes: int = Field(strict=True, ge=1, le=10485760)


class LinkInput(Contract):
    purpose: Literal["REFERENCE", "CORRECTION"] = "REFERENCE"
    source_voucher_id: uuid.UUID
    source_revision_id: uuid.UUID


class AssignmentInput(Contract):
    role: Literal["SELLER", "BROKER", "COLLECTOR", "RETURN_HANDLER", "PAYMENT_HANDLER"]
    principal_id: uuid.UUID
    source_version: int = Field(strict=True, ge=1)
    line_key: uuid.UUID | None = None
    share: Quantity = Decimal("100")
    source_revision_id: uuid.UUID | None = None
    override_reason: str | None = Field(default=None, max_length=500)


class CounterInput(Contract):
    counter_id: uuid.UUID
    session_id: uuid.UUID | None = None


class FulfillmentTermsInput(Contract):
    purpose: Literal["PROCURE", "INTERNAL_ISSUE", "SALE", "PURCHASE", "QUOTE"]
    valid_until: dt.date | None = None
    required_by: dt.date | None = None
    destination_reference: str | None = Field(default=None, min_length=1, max_length=120)
    delivery_terms: str = Field(default="", max_length=1000)
    payment_terms: str = Field(default="", max_length=1000)


class VoucherInput(Contract):
    stock: StockInput | None = None
    financial: MoneyInput | None = None
    invoice: InvoiceInput | None = None
    fulfillment_terms: FulfillmentTermsInput | None = None

    @model_serializer(mode="wrap")
    def stable_legacy_content(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.stock is None:
            result.pop("stock", None)
        if self.financial is None:
            result.pop("financial", None)
        if self.invoice is None:
            result.pop("invoice", None)
        if self.fulfillment_terms is None:
            result.pop("fulfillment_terms", None)
        return result

    type_revision_id: uuid.UUID
    class_id: uuid.UUID | None = None
    document_date: dt.date
    posting_date: dt.date | None = None
    stock_date: dt.date | None = None
    statutory_date: dt.date | None = None
    credit_terms_date: dt.date | None = None
    mode: Literal["ACCOUNTS", "ITEMS", "MIXED"] = "ACCOUNTS"
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    narration: str = Field(default="", max_length=2000)
    lines: tuple[LineInput, ...] = Field(default=(), max_length=200)
    parties: tuple[PartyInput, ...] = Field(default=(), max_length=20)
    references: tuple[ReferenceInput, ...] = Field(default=(), max_length=30)
    attachments: tuple[AttachmentInput, ...] = Field(default=(), max_length=20)
    links: tuple[LinkInput, ...] = Field(default=(), max_length=20)
    assignments: tuple[AssignmentInput, ...] = Field(default=(), max_length=100)
    counter: CounterInput | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if self.stock is not None:
            if tuple(line.line_id for line in self.stock.lines) != tuple(
                line.line_key for line in self.lines
            ):
                raise ValueError(
                    "physical lines must follow the same common item line identities and order"
                )
            # A Purchase bill that adds stock bills exactly what it receives (B24); every other
            # stock voucher moves goods without billing them.
            billing = self.stock.action == "PURCHASE_INVOICE"
            if any(
                (stock.item_id, stock.quantity)
                != (common.item.item_id, common.item.actual_quantity)
                or common.item.billed_quantity != (common.item.actual_quantity if billing else 0)
                for stock, common in zip(self.stock.lines, self.lines, strict=True)
            ):
                raise ValueError(
                    "a purchase bill bills the quantity it receives"
                    if billing
                    else "physical details require the same actual quantity and zero billed "
                    "quantity"
                )
            if billing and (
                self.invoice is None
                or self.financial is not None
                or self.stock.stock_date != self.posting_date
            ):
                raise ValueError(
                    "a purchase bill that adds stock carries its invoice and posts on its "
                    "stock date"
                )
        if (
            self.stock is not None
            and self.stock.action != "PURCHASE_INVOICE"
            and (self.financial is not None or self.invoice is not None)
        ):
            raise ValueError(
                "physical stock uses its native clearing profile; financial entry is exclusive"
            )
        if self.stock is not None and (
            self.stock.stock_date != self.stock_date or self.stock.currency != self.currency
        ):
            raise ValueError("stock movement date and currency must match the voucher header")
        if self.financial is not None and self.invoice is not None:
            raise ValueError("invoice and standalone financial entry are exclusive")
        canonical_json(self.model_dump(mode="json"), maximum_bytes=262144)
        if len({line.line_key for line in self.lines}) != len(self.lines):
            raise ValueError("duplicate logical line keys")
        if len({(a.role, a.line_key, a.principal_id) for a in self.assignments}) != len(
            self.assignments
        ):
            raise ValueError("duplicate commercial assignments")
        return self


class VoucherEdit(Version):
    content: VoucherInput


class VoucherActionRequest(Version):
    """The body of submit, approve, reject, cancel, accept, decline and expire."""

    #: Only ``submit`` accepts it: confirms that a Purchase bill whose supplier bill number is
    #: already recorded is meant to be entered again.
    acknowledge_duplicate_bill: StrictBool = False

    @model_serializer(mode="wrap")
    def _omit_unacknowledged(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Leave the acknowledgement out of the dump unless it is set.

        The dump is hashed into the idempotency request digest. A key stored before the field
        existed was hashed from ``{expected_version, reason}``; always dumping ``false`` would make
        its same-body retry fail as another request. Omitting ``false`` keeps those digests, while
        an acknowledged submit (``true``) still differs from the plain one.
        """
        data: dict[str, Any] = handler(self)
        if data.get("acknowledge_duplicate_bill") is False:
            del data["acknowledge_duplicate_bill"]
        return data


class IssueRequest(Version):
    series_id: uuid.UUID | None = None
    requested_sequence: int | None = Field(default=None, strict=True, ge=1, le=2**63 - 2)
    manual_number: str | None = Field(default=None, min_length=1, max_length=100)


class SeriesCreate(Contract):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{0,19}$")
    prefix: str = Field(default="", pattern=r"^[A-Z0-9/_-]{0,20}$")
    suffix: str = Field(default="", pattern=r"^[A-Z0-9/_-]{0,20}$")
    padding: int = Field(default=6, strict=True, ge=1, le=12)
    start_value: int = Field(default=1, strict=True, ge=1, le=2**63 - 2)
    numbering_mode: Literal["AUTOMATIC", "AUTOMATIC_WITH_OVERRIDE", "MANUAL"] = "AUTOMATIC"
    reset_policy: Literal["FINANCIAL_YEAR", "NEVER"] = "FINANCIAL_YEAR"
    include_year: StrictBool = True


class TemplateCreate(Contract):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{0,39}$")
    title: str = Field(min_length=1, max_length=120)
    fields: tuple[
        Literal[
            "document_date",
            "currency",
            "narration",
            "lines",
            "parties",
            "references",
            "custom_fields",
            "fulfillment_terms",
        ],
        ...,
    ] = Field(default=("document_date", "currency", "narration", "lines"), max_length=12)


class ArtifactCreate(Version):
    template_revision_id: uuid.UUID | None = None
