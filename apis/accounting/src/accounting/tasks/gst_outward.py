"""Validate retained statutory detail against native committed invoice evidence."""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from functools import cache

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.reference import states
from reporting_contract.gst_outward import DOCUMENT_KINDS, MONEY
from reporting_contract.gst_outward import GstOutwardRecord as InputRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.models.gst_outward import GstOutwardRecord
from accounting.models.invoice import InvoiceRecord, InvoiceSupplyFact, InvoiceTaxComponent
from accounting.models.ledger import Journal
from accounting.models.masters import PartyTaxRegistration
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.tasks.finance_records import require_fields


@cache
def state_tax_codes() -> dict[str, str]:
    return {
        row["code"]: row["tax_jurisdiction_code"]
        for row in states()
        if row["country_code"] == "IN" and row["tax_jurisdiction_code"]
    }


async def validate(db: AsyncSession, current: Access, row: InputRecord) -> None:
    company = current.context.company_id
    registration = next(
        (item for item in current.context.registrations if item["id"] == str(row.registration_id)),
        None,
    )
    if (
        not registration
        or registration.get("country_code") != "IN"
        or registration["tax_system"] != "gst_in"
        or registration["regime"]
        not in {"regular", "sez_unit", "sez_developer", "casual_taxable_person"}
    ):
        raise ValidationFailedError(
            "select a company Indian GSTIN with an outward-return obligation"
        )
    if row.document_date < dt.date.fromisoformat(registration["valid_from"]) or (
        registration.get("valid_to")
        and row.document_date >= dt.date.fromisoformat(registration["valid_to"])
    ):
        raise ValidationFailedError("issuing GSTIN was not valid on the retained document date")
    if row.details.prior_filed_channel == "IFF":
        following_month = dt.date(
            row.return_date.year + (row.return_date.month == 12), row.return_date.month % 12 + 1, 1
        )
        if (
            row.kind not in {"INVOICE", "CREDIT_NOTE", "DEBIT_NOTE"}
            or row.return_date.month % 3 == 0
            or row.details.eco_scheme == "9_5"
            or row.details.recipient_type == "UNREGISTERED"
        ):
            raise ValidationFailedError(
                "IFF supports eligible registered invoices and tax notes only"
            )
        if (
            not row.details.prior_filing_date
            or not following_month <= row.details.prior_filing_date <= dt.date.today()
        ):
            raise ValidationFailedError(
                "IFF proof must follow the supply month and cannot be future dated"
            )
        if not any(
            preference["frequency"] == "QRMP"
            and preference["valid_from"] <= row.return_date.isoformat()
            and (
                not preference.get("valid_to")
                or preference["valid_to"] > row.return_date.isoformat()
            )
            for preference in registration.get("filing_preferences", [])
        ):
            raise ValidationFailedError("IFF requires the GSTIN's dated QRMP filing preference")
    original = None
    if row.original_record_id:
        original = await company_object(
            db, GstOutwardRecord, row.original_record_id, company_id=company
        )
        require_fields(current, "gst_outward_record", set(InputRecord.model_fields), row=original)
        if original.registration_id != row.registration_id:
            raise ValidationFailedError("correction must use the original GSTIN")
        note_link = row.kind in {"CREDIT_NOTE", "DEBIT_NOTE"} and original.kind == "INVOICE"
        if note_link and any(
            original.details.get(key) != getattr(row.details, key)
            for key in (
                "recipient_type",
                "recipient_gstin",
                "place_of_supply",
                "supply_type",
                "reverse_charge",
                "eco_scheme",
                "operator_gstin",
            )
        ):
            raise ValidationFailedError(
                "linked notes must retain the original recipient and statutory supply profile"
            )
        if (
            row.kind != "AMENDMENT"
            and not note_link
            and (
                original.kind != row.kind
                or original.return_date != row.return_date
                or row.kind not in {"DOCUMENTS", "PORTAL", "COVERAGE"}
            )
        ):
            raise ValidationFailedError(
                "only supporting evidence may be replaced within its original period"
            )
        if (
            row.kind == "COVERAGE"
            and original.details.get("coverage_area") != row.details.coverage_area
        ):
            raise ValidationFailedError("coverage replacement must retain its original review area")
    if row.kind in DOCUMENT_KINDS and row.kind != "AMENDMENT":
        start_year = (
            row.document_date.year if row.document_date.month >= 4 else row.document_date.year - 1
        )
        duplicate = await db.scalar(
            select(GstOutwardRecord.id)
            .where(
                GstOutwardRecord.company_id == company,
                GstOutwardRecord.registration_id == row.registration_id,
                GstOutwardRecord.kind == row.kind,
                GstOutwardRecord.document_number == row.document_number,
                GstOutwardRecord.document_date >= dt.date(start_year, 4, 1),
                GstOutwardRecord.document_date < dt.date(start_year + 1, 4, 1),
            )
            .limit(1)
        )
        if duplicate:
            raise ConflictError(
                "this outward statutory document is already captured in its GST financial year"
            )
    if row.kind == "AMENDMENT":
        if original is None or original.kind not in DOCUMENT_KINDS:
            raise ValidationFailedError("amendment requires an original supply or note")
        ancestor = original
        for _ in range(32):
            if ancestor.kind != "AMENDMENT":
                break
            if ancestor.original_record_id is None:
                raise ValidationFailedError("amendment baseline has no original evidence")
            ancestor = await company_object(
                db, GstOutwardRecord, ancestor.original_record_id, company_id=company
            )
            require_fields(
                current, "gst_outward_record", set(InputRecord.model_fields), row=ancestor
            )
            if ancestor.registration_id != row.registration_id:
                raise ValidationFailedError("amendment history must retain its GSTIN")
        else:
            raise ValidationFailedError("amendment history exceeds the supported depth")
        if ancestor.kind not in DOCUMENT_KINDS or ancestor.kind == "AMENDMENT":
            raise ValidationFailedError("amendment history must end in a supply, note or advance")
        if original.return_date >= row.return_date:
            raise ValidationFailedError("amendment baseline must precede its revised return date")
        duplicate = await db.scalar(
            select(GstOutwardRecord.id)
            .where(
                GstOutwardRecord.company_id == company,
                GstOutwardRecord.kind == "AMENDMENT",
                GstOutwardRecord.original_record_id == row.original_record_id,
            )
            .limit(1)
        )
        if duplicate:
            raise ConflictError(
                "this baseline already has an amendment; use the latest amended evidence"
            )
    if row.source_entity == "EXTERNAL":
        return
    if row.kind not in {"INVOICE", "CREDIT_NOTE", "DEBIT_NOTE"} or row.source_id is None:
        raise ValidationFailedError("native invoice evidence supports invoices and tax notes only")
    invoice = await company_object(db, InvoiceRecord, row.source_id, company_id=company)
    require_fields(
        current,
        "invoice_record",
        {
            "intent_id",
            "kind",
            "currency",
            "payable",
            "document_date",
            "bill_reference",
            "source_invoice_id",
        },
        row=invoice,
    )
    if invoice.kind != ("SALES" if row.kind == "INVOICE" else row.kind) or (
        invoice.currency != "INR" and row.details.source_currency != invoice.currency
    ):
        raise ValidationFailedError(
            "native outward evidence must match its committed document type and retained INR"
        )
    conversion = Decimal(row.details.conversion_rate or "1")
    if invoice.currency == "INR" and (
        conversion != 1 or row.details.source_currency not in {None, "INR"}
    ):
        raise ValidationFailedError("an INR native document cannot acquire a foreign conversion")
    if (
        row.details.source_invoice_value is not None
        and Decimal(row.details.source_invoice_value) != invoice.payable
    ):
        raise ValidationFailedError("conversion must retain the native invoice value and currency")

    def converted(value: Decimal) -> Decimal:
        return (value * conversion).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    if invoice.source_invoice_id:
        original_invoice = await company_object(
            db, InvoiceRecord, invoice.source_invoice_id, company_id=company
        )
        require_fields(current, "invoice_record", {"kind"}, row=original_invoice)
        if original_invoice.kind != "SALES":
            raise ValidationFailedError("purchase notes are not outward GSTR-1 supplies")
    intent = await company_object(db, VoucherMoneyIntent, invoice.intent_id, company_id=company)
    if intent.status != "COMMITTED" or intent.journal_id is None:
        raise ConflictError("only committed financial documents enter an outward return")
    journal = await company_object(db, Journal, intent.journal_id, company_id=company)
    require_fields(current, "journal", {"status"}, row=journal)
    if journal.status != "POSTED":
        raise ConflictError("native supply journal must be posted")
    if (
        invoice.document_date != row.document_date
        or invoice.bill_reference != row.document_number
        or converted(invoice.payable) != Decimal(row.invoice_value)
    ):
        raise ValidationFailedError(
            "outward number, date and invoice value must match the committed document"
        )
    supplies = list(
        await db.scalars(
            select(InvoiceSupplyFact)
            .where(
                InvoiceSupplyFact.company_id == company, InvoiceSupplyFact.invoice_id == invoice.id
            )
            .limit(201)
        )
    )
    provided = {item.source_line_id: item for item in row.details.items}
    if (
        len(supplies) > 200
        or len(provided) != len(row.details.items)
        or set(provided) != {supply.id for supply in supplies}
    ):
        raise ValidationFailedError("all committed supply lines must be represented exactly once")
    for supply in supplies:
        require_fields(
            current,
            "invoice_supply_fact",
            {
                "company_registration_id",
                "party_registration_id",
                "taxable",
                "supply_kind",
                "classification_code",
                "treatment",
                "reverse_charge",
                "place_of_supply",
                "supply_context",
            },
            row=supply,
        )
        item = provided[supply.id]
        if (
            supply.company_registration_id != row.registration_id
            or converted(supply.taxable) != Decimal(item.taxable)
            or supply.treatment != item.treatment
            or supply.reverse_charge != row.details.reverse_charge
            or ("SERVICES" if supply.supply_kind == "SERVICE" else supply.supply_kind)
            != item.goods_service
        ):
            raise ValidationFailedError(
                "statutory detail differs from the committed supply profile"
            )
        if supply.classification_code and supply.classification_code != item.hsn:
            raise ValidationFailedError("HSN/SAC differs from the retained supply classification")
        if (
            supply.supply_context not in {"INTER_STATE", "INTRA_STATE", "INTRA_UT"}
            or row.details.supply_type != "DOMESTIC"
            or row.details.eco_scheme
        ):
            raise ValidationFailedError(
                "exports, SEZ, ECO and special profiles require retained special statutory evidence"
            )
        if (supply.supply_context == "INTER_STATE") != (
            row.details.place_of_supply != registration["number"][:2]
        ):
            raise ValidationFailedError("place of supply differs from the native tax jurisdiction")
        if state_tax_codes().get(supply.place_of_supply or "") != row.details.place_of_supply:
            raise ValidationFailedError("place of supply differs from the retained native state")
        if supply.party_registration_id:
            party_registration = await company_object(
                db, PartyTaxRegistration, supply.party_registration_id, company_id=company
            )
            require_fields(
                current,
                "party_tax_registration",
                {"registration_number", "registration_type", "scheme"},
                row=party_registration,
            )
            if (
                row.details.recipient_gstin != party_registration.registration_number
                or row.details.recipient_type == "UNREGISTERED"
            ):
                raise ValidationFailedError(
                    "recipient identifier differs from the native registration"
                )
        elif row.details.recipient_type != "UNREGISTERED":
            raise ValidationFailedError("native supply has no registered recipient evidence")
        components = list(
            await db.scalars(
                select(InvoiceTaxComponent)
                .where(
                    InvoiceTaxComponent.company_id == company,
                    InvoiceTaxComponent.supply_id == supply.id,
                )
                .limit(201)
            )
        )
        if len(components) > 200:
            raise ValidationFailedError("native tax components exceed the supported line bound")
        require_fields(current, "invoice_tax_component", {"amount", "code", "percentage"})
        expected = {head: Decimal(0) for head in MONEY[1:]}
        rate = Decimal(0)
        for component in components:
            head = {
                "IGST": "igst",
                "CGST": "cgst",
                "SGST": "sgst",
                "UTGST": "sgst",
                "CESS": "cess",
            }.get(component.code)
            if head:
                expected[head] += abs(converted(component.amount))
            if head in {"igst", "cgst", "sgst"} and component.percentage is not None:
                rate += component.percentage
        if rate != Decimal(item.rate):
            raise ValidationFailedError("GST rate differs from committed tax components")
        if any(expected[head] != Decimal(getattr(item, head)) for head in expected):
            raise ValidationFailedError("outward tax details must match committed tax components")
