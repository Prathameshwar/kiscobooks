"""Company-fenced, audited and idempotent statutory evidence capture."""

from decimal import ROUND_HALF_UP, Decimal

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from reporting_contract.gst import GstReturnRecord as InputRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.domain.reference import tax_jurisdictions
from accounting.models.gst_return import GstReturnRecord
from accounting.models.invoice import (
    InvoicePostingLine,
    InvoiceRecord,
    InvoiceSupplyFact,
    InvoiceTaxComponent,
)
from accounting.models.invoice_credit import InvoiceCreditAction, InvoiceCreditEvent
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import PartyTaxRegistration
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.models.voucher_tax import JournalTax
from accounting.tasks.finance_records import require_fields

FIELDS = ("taxable", "igst", "cgst", "sgst", "cess")
TREATMENTS = {
    "3.1a": {"TAXABLE"},
    "3.1b": {"TAXABLE"},
    "3.2": {"TAXABLE"},
    "3.1c": {"NIL_RATED", "EXEMPT"},
    "3.1e": {"NON_GST"},
    "INWARD_TAXABLE": {"TAXABLE"},
    "3.1d": {"TAXABLE"},
    "5_EXEMPT_INTER": {"NIL_RATED", "EXEMPT"},
    "5_EXEMPT_INTRA": {"NIL_RATED", "EXEMPT"},
    "5_NONGST_INTER": {"NON_GST"},
    "5_NONGST_INTRA": {"NON_GST"},
}


def classification(
    row: InputRecord, treatments: set[str], reverse: bool, zero: bool, context: str | None
) -> None:
    if row.category in {"3.1.1i", "3.1.1ii"}:
        raise ValidationFailedError("section 9(5) requires explicitly reviewed statutory evidence")
    expected = TREATMENTS.get(row.category)
    if expected is not None and (not treatments or not treatments <= expected):
        raise ValidationFailedError("allocation differs from the committed supply treatment")
    if (row.category == "3.1b" and not zero) or (row.category in {"3.1a", "3.2"} and zero):
        raise ValidationFailedError("zero-rated classification requires retained source evidence")
    if row.category in {"3.1d", "INWARD_TAXABLE"} and reverse != (row.category == "3.1d"):
        raise ValidationFailedError("reverse-charge classification differs from the native supply")
    if row.category.startswith("5_"):
        inter = row.category.endswith("_INTER")
        if (inter and context != "INTER_STATE") or (
            not inter and context not in {"INTRA_STATE", "INTRA_UT"}
        ):
            raise ValidationFailedError(
                "inward disclosure must match the native supply jurisdiction"
            )


async def validate(db: AsyncSession, current: Access, row: InputRecord) -> None:
    company = current.context.company_id
    if row.source_entity != "EXTERNAL" and row.source_id is None:
        raise ValidationFailedError("native source identity is required")
    registration = next(
        (item for item in current.context.registrations if item["id"] == str(row.registration_id)),
        None,
    )
    if (
        registration is None
        or registration.get("country_code", "IN") != "IN"
        or registration["tax_system"] != "gst_in"
        or registration["regime"]
        not in {"regular", "sez_unit", "sez_developer", "casual_taxable_person"}
    ):
        raise ValidationFailedError("select a company GSTIN which files GSTR-3B")
    if row.source_entity != "EXTERNAL":
        duplicate = await db.scalar(
            select(GstReturnRecord.id)
            .where(
                GstReturnRecord.company_id == company,
                GstReturnRecord.registration_id == row.registration_id,
                GstReturnRecord.source_entity == row.source_entity,
                GstReturnRecord.source_id == row.source_id,
                GstReturnRecord.category == row.category,
            )
            .limit(1)
        )
        if duplicate:
            raise ConflictError("this statutory source is already allocated")
    if row.source_entity == "invoice_supply_fact":
        assert row.source_id is not None
        supply = await company_object(db, InvoiceSupplyFact, row.source_id, company_id=company)
        require_fields(
            current,
            "invoice_supply_fact",
            {"company_registration_id", "invoice_id", "taxable"},
            row=supply,
        )
        if supply.company_registration_id != row.registration_id:
            raise ValidationFailedError("supply belongs to a different GSTIN")
        invoice = await company_object(db, InvoiceRecord, supply.invoice_id, company_id=company)
        require_fields(current, "invoice_record", {"intent_id", "kind", "currency"}, row=invoice)
        intent = await company_object(db, VoucherMoneyIntent, invoice.intent_id, company_id=company)
        # Execution intents are internal owner controls, without a public field-policy resource.
        if intent.status != "COMMITTED" or intent.journal_id is None:
            raise ConflictError("only committed supplies enter a statutory return")
        journal = await company_object(db, Journal, intent.journal_id, company_id=company)
        require_fields(current, "journal", {"status"}, row=journal)
        if journal.status != "POSTED":
            raise ConflictError("GST source journal is not posted")
        conversion = Decimal(1)
        if invoice.currency == "INR" and row.conversion_rate is not None:
            if Decimal(row.conversion_rate) != conversion:
                raise ValidationFailedError("an INR source cannot carry a foreign conversion rate")
        if invoice.currency != "INR":
            lines = list(
                await db.scalars(
                    select(JournalLine)
                    .join(
                        InvoicePostingLine,
                        (InvoicePostingLine.company_id == JournalLine.company_id)
                        & (InvoicePostingLine.journal_line_id == JournalLine.id),
                    )
                    .where(
                        InvoicePostingLine.company_id == company,
                        InvoicePostingLine.invoice_id == invoice.id,
                        InvoicePostingLine.line_key == supply.line_key,
                    )
                    .limit(201)
                )
            )
            require_fields(current, "journal_line", {"base_currency", "exchange_rate"})
            rates = {line.exchange_rate for line in lines if line.base_currency == "INR"}
            if (
                not lines
                or len(lines) > 200
                or len(rates) != 1
                or any(line.base_currency != "INR" for line in lines)
            ):
                raise ConflictError("retained supply conversion is missing or ambiguous")
            conversion = rates.pop()
            if row.conversion_rate is None or Decimal(row.conversion_rate) != conversion:
                raise ValidationFailedError(
                    "statutory INR conversion must match the committed source rate"
                )
        outward = invoice.kind in {"SALES", "CREDIT_NOTE"}
        allowed = (
            {"3.1a", "3.1b", "3.1c", "3.1e", "3.1.1i", "3.1.1ii", "3.2"}
            if outward
            else {
                "3.1d",
                "INWARD_TAXABLE",
                "5_EXEMPT_INTER",
                "5_EXEMPT_INTRA",
                "5_NONGST_INTER",
                "5_NONGST_INTRA",
            }
        )
        if row.category not in allowed:
            raise ValidationFailedError("allocation does not match the supply direction")
        require_fields(
            current,
            "invoice_supply_fact",
            {
                "treatment",
                "reverse_charge",
                "supply_context",
                "source_evidence",
                "tax_point_date",
                "party_registration_id",
                "place_of_supply",
            },
            row=supply,
        )
        zero_rated = bool(supply.source_evidence.get("zero_rated"))
        classification(
            row, {supply.treatment}, supply.reverse_charge, zero_rated, supply.supply_context
        )
        if row.category == "3.2":
            party_type = "UNREGISTERED"
            if supply.party_registration_id:
                party_registration = await company_object(
                    db,
                    PartyTaxRegistration,
                    supply.party_registration_id,
                    company_id=company,
                )
                require_fields(
                    current, "party_tax_registration", {"registration_type"}, row=party_registration
                )
                party_type = party_registration.registration_type
            if (
                party_type != row.recipient
                or supply.supply_context != "INTER_STATE"
                or tax_jurisdictions().get(supply.place_of_supply or "") != row.place_of_supply
            ):
                raise ValidationFailedError(
                    "table 3.2 recipient and place of supply must match the source"
                )
        sign = Decimal(-1 if invoice.kind in {"CREDIT_NOTE", "DEBIT_NOTE"} else 1)
        expected = dict.fromkeys(FIELDS, Decimal(0))
        expected["taxable"] = (sign * supply.taxable * conversion).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
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
            raise ConflictError("supply tax component capacity exceeded")
        require_fields(current, "invoice_tax_component", {"amount", "code"})
        for component in components:
            head = {
                "IGST": "igst",
                "CGST": "cgst",
                "SGST": "sgst",
                "UTGST": "sgst",
                "CESS": "cess",
            }.get(component.code)
            if head:
                expected[head] += (sign * component.amount * conversion).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
        if row.category == "3.2":
            expected["cgst"] = expected["sgst"] = expected["cess"] = Decimal(0)
        if any(Decimal(getattr(row, head)) != expected[head] for head in FIELDS):
            raise ValidationFailedError("allocation amounts must match the committed supply")
    elif row.source_entity == "invoice_credit_action":
        assert row.source_id is not None
        action = await company_object(db, InvoiceCreditAction, row.source_id, company_id=company)
        require_fields(
            current,
            "invoice_credit_action",
            {"component_id", "amount", "kind", "currency"},
            row=action,
        )
        committed = await db.scalar(
            select(InvoiceCreditEvent).where(
                InvoiceCreditEvent.company_id == company,
                InvoiceCreditEvent.action_id == action.id,
            )
        )
        if committed is None:
            raise ConflictError("only committed input-credit actions enter a statutory return")
        require_fields(
            current,
            "invoice_credit_event",
            {"action_id", "invoice_id"},
            row=committed,
        )
        component = await company_object(
            db, InvoiceTaxComponent, action.component_id, company_id=company
        )
        supply = await company_object(
            db, InvoiceSupplyFact, component.supply_id, company_id=company
        )
        require_fields(current, "invoice_tax_component", {"supply_id", "code"}, row=component)
        require_fields(
            current,
            "invoice_supply_fact",
            {"company_registration_id", "reverse_charge", "tax_profile"},
            row=supply,
        )
        if supply.company_registration_id != row.registration_id or action.currency != "INR":
            raise ValidationFailedError(
                "credit allocation requires the same GSTIN and retained INR"
            )
        if action.kind == "CLAIM":
            if row.category in {"4A1", "4A2", "4A4"}:
                raise ValidationFailedError(
                    "imports and ISD require retained special statutory evidence"
                )
            if supply.tax_profile not in {
                "INDIA_DOMESTIC_SERVICE",
                "INDIA_DOMESTIC_SERVICE_RCM",
            } or row.category != ("4A3" if supply.reverse_charge else "4A5"):
                raise ValidationFailedError(
                    "credit allocation must match the native supply's reverse-charge treatment"
                )
        if action.kind == "BLOCK" and row.category == "4D2":
            raise ValidationFailedError(
                "Table 4(D)(2) requires retained section 16(4) or place-of-supply evidence; "
                "a generic blocked-credit instruction does not establish that classification"
            )
        allowed = {
            "CLAIM": {"4A3", "4A5"},
            "REVERSE_PAYMENT": {"4B2"},
            "RECLAIM_PAYMENT": {"4A5", "4D1"},
            "BLOCK": {"INWARD_INELIGIBLE"},
            "RCM_DISCHARGE": {"OFFSET_RCM_CASH"},
        }.get(action.kind, set())
        head = {
            "IGST": "igst",
            "CGST": "cgst",
            "SGST": "sgst",
            "UTGST": "sgst",
            "CESS": "cess",
        }.get(component.code)
        if (
            row.category not in allowed
            or head is None
            or Decimal(getattr(row, head)) != action.amount
            or any(Decimal(getattr(row, field)) for field in FIELDS if field != head)
        ):
            raise ValidationFailedError(
                "credit allocation must match the committed action and tax head"
            )
    elif row.source_entity == "journal":
        assert row.source_id is not None
        journal = await company_object(db, Journal, row.source_id, company_id=company)
        require_fields(current, "journal", {"status", "base_currency", "kind"}, row=journal)
        if journal.status != "POSTED" or journal.base_currency != "INR":
            raise ConflictError("statutory journal evidence must be posted in INR")
        if not row.explanation:
            raise ValidationFailedError("journal classifications require an explanation")
        if row.category != "COVERAGE":
            tax = await db.scalar(
                select(JournalTax).where(
                    JournalTax.company_id == company,
                    JournalTax.journal_id == journal.id,
                )
            )
            if (
                tax is None
                or tax.company_registration_id != row.registration_id
                or tax.currency != "INR"
            ):
                raise ValidationFailedError(
                    "use a native GST tax analysis or retained external portal evidence"
                )
            require_fields(
                current,
                "journal_tax",
                {
                    "snapshot",
                    "company_registration_id",
                    "taxable_value",
                    "direction",
                    "reverse_charge",
                    "currency",
                    "place_of_supply",
                    "supply_context",
                },
                row=tax,
            )
            allowed = (
                {"3.1a", "3.1b", "3.1c", "3.1e", "3.1.1i", "3.1.1ii", "3.2"}
                if tax.direction == "SALE"
                else {
                    "3.1d",
                    "INWARD_TAXABLE",
                    "5_EXEMPT_INTER",
                    "5_EXEMPT_INTRA",
                    "5_NONGST_INTER",
                    "5_NONGST_INTRA",
                }
            )
            if row.category not in allowed:
                raise ValidationFailedError(
                    "journal allocation does not match its native tax direction"
                )
            if row.conversion_rate is not None and Decimal(row.conversion_rate) != 1:
                raise ValidationFailedError("an INR journal cannot carry a foreign conversion rate")
            computation = tax.snapshot.get("computation") or {}
            classification(
                row,
                {line["treatment"] for line in tax.snapshot.get("lines", [])},
                tax.reverse_charge,
                bool(computation.get("zero_rated")),
                tax.supply_context,
            )
            if row.category == "3.2" and (
                tax.snapshot.get("party_type") != row.recipient
                or tax.supply_context != "INTER_STATE"
                or tax_jurisdictions().get(tax.place_of_supply or "") != row.place_of_supply
            ):
                raise ValidationFailedError(
                    "table 3.2 recipient and place of supply must match the source"
                )
            sign = Decimal(
                -1
                if "RETURN" in journal.kind or journal.kind in {"CREDIT_NOTE", "DEBIT_NOTE"}
                else 1
            )
            expected = dict.fromkeys(FIELDS, Decimal(0))
            expected["taxable"] = sign * tax.taxable_value
            for component in (tax.snapshot.get("computation") or {}).get("component_totals", []):
                head = {
                    "IGST": "igst",
                    "CGST": "cgst",
                    "SGST": "sgst",
                    "UTGST": "sgst",
                    "CESS": "cess",
                }.get(component["component"])
                if head:
                    expected[head] += sign * Decimal(component["tax_amount"])
            if row.category == "3.2":
                expected["cgst"] = expected["sgst"] = expected["cess"] = Decimal(0)
            if any(Decimal(getattr(row, head)) != expected[head] for head in FIELDS):
                raise ValidationFailedError(
                    "journal allocation must match retained GST tax analysis"
                )
    elif not row.explanation:
        raise ValidationFailedError(
            "external evidence requires a description of the source and allocation"
        )
    if row.original_record_id:
        original = await company_object(
            db, GstReturnRecord, row.original_record_id, company_id=company
        )
        if original.registration_id != row.registration_id:
            raise ValidationFailedError("original allocation belongs to another GSTIN")
        if row.category == "4D1":
            if original.category != "4B2" or original.return_date >= row.return_date:
                raise ValidationFailedError(
                    "reclaim must refer to a prior-period temporary reversal"
                )
            prior = list(
                await db.scalars(
                    select(GstReturnRecord)
                    .where(
                        GstReturnRecord.company_id == company,
                        GstReturnRecord.original_record_id == original.id,
                        GstReturnRecord.category == "4D1",
                    )
                    .limit(201)
                )
            )
            if len(prior) > 200 or any(
                sum((getattr(item, head) for item in prior), Decimal(0))
                + Decimal(getattr(row, head))
                > getattr(original, head)
                for head in FIELDS
            ):
                raise ValidationFailedError("reclaim exceeds the original reversal")
