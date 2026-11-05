"""Persist accepted calculation facts and links to the sole native journal amount store."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.invoice import InvoiceCalculationDetail, InvoiceInput, InvoicePreviewCommand
from voucher_execution.money import MoneyInput

from accounting.api.auth import Access
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models import invoice as m
from accounting.models.masters import Record
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.tasks.access import writable
from accounting.tasks.journal_drafts import lines
from accounting.tasks.voucher_money_effects import audit, values


def add_fact(db: AsyncSession, access: Access, row: Record) -> None:
    spec = FINANCIAL_BY_NAME[row.__tablename__]
    native = {
        key: getattr(row, key)
        for key in spec.detail.model_fields
        if key
        not in {
            "id",
            "company_id",
            "row_version",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        }
    }
    writable(access, spec, {}, native)
    db.add(row)


async def store(
    db: AsyncSession,
    access: Access,
    intent: VoucherMoneyIntent,
    request: InvoicePreviewCommand,
    result: InvoiceCalculationDetail,
    financial: MoneyInput,
) -> m.InvoiceRecord:
    body = request.invoice
    if body.accepted_calculation_hash != result.calculation_hash or intent.journal_id is None:
        raise ConflictError("invoice facts require an accepted calculation and prepared journal")
    if (intent.tenant_id, intent.company_id) != (request.tenant_id, request.company_id):
        raise ConflictError("invoice calculation scope differs from its posting intent")
    row = m.InvoiceRecord(
        **values(access),
        intent_id=intent.id,
        revision_id=uuid.UUID(intent.command["revision_id"]),
        source_invoice_id=body.source_invoice_id,
        calculation_version=result.calculation_version,
        calculation_hash=result.calculation_hash,
        configuration_hash=request.configuration_hash,
        company_configuration_hash=request.company_configuration_hash,
        kind=request.kind,
        currency=request.currency,
        document_date=request.document_date,
        posting_date=request.posting_date,
        party_account_id=body.party_account_id,
        bill_reference=body.bill_reference,
        due_date=body.due_date,
        commercial_total=result.commercial_total,
        tax_total=result.tax_total,
        charged_tax_total=result.charged_tax_total,
        rounding=result.rounding,
        payable=result.payable,
        supplier_declared_total=body.supplier_declared_total,
        supplier_difference=result.supplier_difference,
        supplier_difference_reason=body.supplier_difference_reason,
    )
    add_fact(db, access, row)
    await db.flush()
    source_lines = {line.line_key: line for line in body.supplies}
    evidence: dict[str, Any] = {str(item["line_key"]): item for item in result.tax_evidence}
    supplies = {}
    for sequence, line in enumerate(result.lines, 1):
        source = source_lines[line.key]
        tax = source.tax or body.tax
        proof = evidence[str(line.key)] | {
            "item_line_key": str(source.item_line_key) if source.item_line_key else None
        }
        point = proof.get("tax_point", {})
        supply = m.InvoiceSupplyFact(
            **values(access),
            invoice_id=row.id,
            line_key=line.key,
            sequence=sequence,
            account_id=source.account_id,
            supply_kind=source.supply_kind,
            description=source.description,
            entered=line.entered,
            commercial=line.commercial,
            taxable=line.taxable,
            price_rounding=line.price_rounding,
            payable=line.payable,
            tax_profile=tax.profile,
            date_contract_version=2,
            tax_point_date=dt.date.fromisoformat(point["tax_point_date"]) if point else None,
            tax_point_basis=point.get("legal_basis"),
            service_completion_date=tax.service_completion_date,
            company_registration_id=tax.company_registration_id,
            party_registration_id=tax.party_registration_id,
            place_of_supply=tax.place_of_supply,
            supply_context=proof.get("supply_context"),
            # Services carry their SAC, goods their HSN (invoice_tax evidence).
            classification_code=proof.get("sac") or proof.get("hsn"),
            treatment=proof["treatment"],
            reverse_charge=proof.get("reverse_charge", False),
            credit_state=proof["credit_state"],
            supplier_invoice_number=tax.supplier_invoice_number,
            supplier_invoice_date=tax.supplier_invoice_date,
            source_evidence=proof,
        )
        add_fact(db, access, supply)
        supplies[line.key] = supply
    components = {}
    source_components = {item.component_key: item for item in body.components}
    for sequence, item in enumerate(result.components, 1):
        source_component = source_components[item.key]
        component = m.InvoiceComponentFact(
            **values(access),
            invoice_id=row.id,
            component_key=item.key,
            sequence=sequence,
            purpose=source_component.purpose,
            scope=source_component.scope,
            effect=source_component.effect,
            input_kind=source_component.input_kind,
            basis_amount=item.basis_amount,
            basis_quantity=item.basis_quantity,
            input_amount=item.input_amount,
            amount=item.amount,
            account_id=source_component.account_id,
            commercial_treatment=source_component.commercial_treatment,
            tax_treatment=source_component.tax_treatment,
            return_treatment=source_component.return_treatment,
            source_evidence=source_component.source_evidence,
        )
        add_fact(db, access, component)
        components[item.key] = component
    await db.flush()
    for share in result.allocations:
        add_fact(
            db,
            access,
            m.InvoiceAllocationFact(
                **values(access),
                invoice_id=row.id,
                component_id=components[share.component_key].id,
                supply_id=supplies[share.line_key].id,
                purpose=share.purpose,
                amount=share.amount,
            ),
        )
    tax_postings: dict[uuid.UUID, tuple[uuid.UUID | None, str | None]] = {}
    for line in result.lines:
        recipes = {part["id"]: part for part in evidence[str(line.key)].get("components", [])}
        for part in line.taxes:
            recipe = recipes[part.key]
            tax_component = m.InvoiceTaxComponent(
                **values(access),
                invoice_id=row.id,
                supply_id=supplies[line.key].id,
                component_key=part.key,
                code=part.code,
                basis=part.basis,
                amount=part.amount,
                percentage=recipe["percentage"],
                supplier_charged=part.supplier_charged,
                rounding_mode=recipe["rounding_mode"],
                source_version=recipe["source_version"],
            )
            add_fact(db, access, tax_component)
            for purpose in ("OUTPUT_" + part.code, "PENDING_" + part.code, "RCM_" + part.code):
                tax_postings[uuid.uuid5(line.key, purpose + ":" + part.key)] = (
                    tax_component.id,
                    purpose,
                )
            tax_postings[uuid.uuid5(line.key, "nonrecoverable:" + part.key)] = (
                tax_component.id,
                "NONRECOVERABLE",
            )
    # Tax rows must exist before links reference them; these mappers have no ORM relationships.
    await db.flush()
    journal_lines = await lines(db, intent.company_id, intent.journal_id)
    for sequence, (entry, journal_line) in enumerate(
        zip(financial.accounts, journal_lines, strict=True), 1
    ):
        if (entry.account_id, entry.side, entry.currency, entry.amount, entry.exchange_rate) != (
            journal_line.account_id,
            journal_line.side,
            journal_line.currency,
            journal_line.amount,
            journal_line.exchange_rate,
        ):
            raise ConflictError("prepared GL differs from the accepted invoice calculation")
        add_fact(
            db,
            access,
            m.InvoicePostingLine(
                **values(access),
                invoice_id=row.id,
                journal_line_id=journal_line.id,
                tax_component_id=tax_postings.get(entry.line_key, (None, None))[0],
                tax_purpose=tax_postings.get(entry.line_key, (None, None))[1],
                line_key=entry.line_key,
                sequence=sequence,
                source_version=entry.source_version,
                purpose=entry.purpose,
                tracking=entry.tracking,
                bill_reference=entry.bill_reference,
                due_date=entry.due_date,
            ),
        )
    await db.flush()
    audit(db, access, row.id, "invoice_record", "prepare")
    return row


async def load_money(db: AsyncSession, intent: VoucherMoneyIntent) -> MoneyInput:
    """Reconstruct only from the owner journal and its immutable accepted source links."""
    from accounting.tasks.invoice_execution import allocations as invoice_allocations

    row = await db.scalar(
        select(m.InvoiceRecord).where(
            m.InvoiceRecord.company_id == intent.company_id,
            m.InvoiceRecord.intent_id == intent.id,
        )
    )
    if row is None or intent.journal_id is None:
        raise ConflictError("invoice calculation facts are missing")
    native = await lines(db, intent.company_id, intent.journal_id)
    links = list(
        await db.scalars(
            select(m.InvoicePostingLine)
            .where(
                m.InvoicePostingLine.company_id == intent.company_id,
                m.InvoicePostingLine.invoice_id == row.id,
            )
            .order_by(m.InvoicePostingLine.sequence)
            .limit(201)
        )
    )
    if len(links) != len(native):
        raise ConflictError("invoice journal links are incomplete")
    body = InvoiceInput.model_validate(intent.command["source_payload"]["invoice"])
    if body.accepted_calculation_hash != row.calculation_hash:
        raise ConflictError("invoice accepted calculation differs from the owner record")
    entries = []
    for link, entry in zip(links, native, strict=True):
        if link.journal_line_id != entry.id:
            raise ConflictError("invoice journal line order differs from its accepted links")
        entries.append(
            {
                "line_key": link.line_key,
                "account_id": entry.account_id,
                "source_version": link.source_version,
                "side": entry.side,
                "currency": entry.currency,
                "amount": entry.amount,
                "exchange_rate": entry.exchange_rate,
                "description": entry.description or "",
                "purpose": link.purpose,
                "tracking": link.tracking,
                "bill_reference": link.bill_reference,
                "due_date": link.due_date,
            }
        )
    return MoneyInput.model_validate(
        {
            "accounts": entries,
            "tenders": [row.tender for row in body.tenders],
                "allocations": invoice_allocations(body, row.kind),
        }
    )
