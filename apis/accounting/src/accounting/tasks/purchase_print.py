"""Reuse immutable posted invoice facts; current drafts use the owner calculator."""

import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.invoice import InvoiceCalculationDetail
from voucher_execution.printing import (
    PrintLedger,
    PrintLine,
    PurchasePrintCommand,
    PurchasePrintFacts,
)

from accounting.api.auth import Access
from accounting.api.invoices import posted
from accounting.models import invoice as m
from accounting.models.ledger import Journal
from accounting.models.masters import Account, Party
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.resources import BY_NAME
from accounting.tasks.access import authorize
from accounting.tasks.finance_records import require_fields
from accounting.tasks.invoice_calculation import preview
from accounting.tasks.invoice_goods import GoodsFacts


async def party_name(db: AsyncSession, current: Access, account: Account) -> str | None:
    """The supplier party's own current name, or None when this actor may not read it.

    The payable account's name (for example "Acme - Payable") is a ledger label, not the
    supplier. The party is separate data under its own read permission and field policy, so
    an unreadable name is withheld (the print says "Supplier details restricted") and is never
    replaced by the account label.
    """
    if account.party_id is None:
        return None
    party = await company_object(db, Party, account.party_id, company_id=account.company_id)
    try:
        require_fields(current, "party", {"name"}, row=party)
    except PermissionDeniedError:
        return None
    return party.name


async def ledger_names(
    db: AsyncSession,
    current: Access,
    company_id: uuid.UUID,
    lines: dict[uuid.UUID, uuid.UUID],
    tenders: dict[uuid.UUID, uuid.UUID],
) -> tuple[PrintLedger, ...]:
    """Each printed line's or tender's ledger name, `None` where this actor may not read it.

    `lines` maps an invoice `line_key`, and `tenders` a `tender_key`, to its account. Account
    read permission is already required by the caller; the name is then checked per row, so a
    conditional field policy that hides one ledger leaves the others readable. A name that
    cannot be read is withheld (the print shows a neutral label), never replaced by another.
    """
    if lines.keys() & tenders.keys():
        raise ConflictError("a Purchase line and a settlement share one identity")
    targets = lines | tenders
    wanted = set(targets.values())
    accounts = {
        row.id: row
        for row in await db.scalars(
            select(Account)
            .where(Account.company_id == company_id, Account.id.in_(wanted))
            .limit(len(wanted) + 1)
        )
    }
    if wanted - accounts.keys():
        raise ConflictError("a ledger account on this Purchase is unavailable")
    names: dict[uuid.UUID, str | None] = {}
    for identity, account in accounts.items():
        try:
            require_fields(current, "account", {"name"}, row=account)
        except PermissionDeniedError:
            names[identity] = None
        else:
            names[identity] = account.name
    return tuple(PrintLedger(key=key, name=names[targets[key]]) for key in sorted(targets, key=str))


async def journal_number(db: AsyncSession, current: Access, record: m.InvoiceRecord) -> str | None:
    """The number of the journal that posted this invoice record, or None when unreadable.

    `posted()` has already proved the journal exists, is POSTED and is readable at all, so a
    posted journal always has its number; only a field policy on `number` can withhold it.
    """
    intent = await company_object(
        db, VoucherMoneyIntent, record.intent_id, company_id=record.company_id
    )
    if intent.journal_id is None:
        raise ConflictError("invoice has not been posted")
    journal = await company_object(db, Journal, intent.journal_id, company_id=record.company_id)
    try:
        require_fields(current, "journal", {"number"}, row=journal)
    except PermissionDeniedError:
        return None
    return journal.number


def print_lines(
    command: PurchasePrintCommand,
    codes: dict[uuid.UUID, str | None],
    goods: GoodsFacts | None,
) -> tuple[PrintLine, ...]:
    """Each supply's HSN/SAC and, for goods, its base unit's label.

    ``codes`` is what the line was taxed under (preview evidence or the posted supply fact).
    A unit label comes only from Catalog's facts for this bill's own stock line; a goods line
    whose facts are absent prints without one rather than with a guess.
    """
    rows = []
    for supply in command.preview.invoice.supplies:
        label = None
        if goods is not None and supply.supply_kind == "GOODS" and supply.item_line_key:
            line = goods.lines.get(supply.item_line_key)
            item = goods.items.get(line.item_id) if line is not None else None
            label = item.base_unit_label if item is not None else None
        code = codes.get(supply.line_key)
        rows.append(
            PrintLine(
                key=supply.line_key,
                classification_code=code if code and code.isdigit() else None,
                unit_label=label,
            )
        )
    return tuple(rows)


def evidence_codes(calculation: InvoiceCalculationDetail) -> dict[uuid.UUID, str | None]:
    """The HSN (goods) or SAC (services) a preview calculation taxed each line under."""
    codes: dict[uuid.UUID, str | None] = {}
    for row in calculation.tax_evidence:
        code = row.get("sac") or row.get("hsn")
        codes[uuid.UUID(str(row["line_key"]))] = str(code) if code else None
    return codes


async def facts(
    db: AsyncSession,
    current: Access,
    body: PurchasePrintCommand,
    goods: GoodsFacts | None = None,
) -> PurchasePrintFacts:
    """``goods`` are the bill's Catalog item facts with labels, read before this session."""
    command = body.preview
    current.actor.require_scope("vouchers.read", target=ScopePath(company_id=command.company_id))
    if command.kind != "PURCHASE":
        raise ConflictError("Purchase print facts require a Purchase invoice")
    authorize(current, BY_NAME["account"], "read")
    account = await company_object(
        db, Account, command.invoice.party_account_id, company_id=command.company_id
    )
    require_fields(current, "account", {"name"}, row=account)
    supplier_name = await party_name(db, current, account)
    settlement_targets = {row.tender.tender_key: row.account_id for row in command.invoice.tenders}
    if not body.require_posted:
        calculation = await preview(db, current, command, goods=goods)
        return PurchasePrintFacts(
            calculation=calculation,
            supplier_name=supplier_name,
            source="PREVIEW",
            lines=print_lines(body, evidence_codes(calculation), goods),
            ledgers=await ledger_names(
                db,
                current,
                command.company_id,
                {row.line_key: row.account_id for row in command.invoice.supplies},
                settlement_targets,
            ),
        )
    rows = list(
        await db.scalars(
            select(m.InvoiceRecord)
            .where(
                m.InvoiceRecord.company_id == command.company_id,
                m.InvoiceRecord.revision_id == body.revision_id,
            )
            .limit(2)
        )
    )
    if len(rows) != 1:
        raise ConflictError("a unique posted Purchase record is required")
    record = await posted(db, current, rows[0].id)
    fields = {
        "kind",
        "revision_id",
        "configuration_hash",
        "party_account_id",
        "currency",
        "calculation_hash",
        "commercial_total",
        "tax_total",
        "charged_tax_total",
        "rounding",
        "payable",
        "supplier_difference",
    }
    require_fields(current, "invoice_record", fields, row=record)
    if (
        record.kind != "PURCHASE"
        or record.currency != command.currency
        or record.party_account_id != account.id
        or record.configuration_hash != command.configuration_hash
        or record.calculation_hash != command.invoice.accepted_calculation_hash
    ):
        raise ConflictError("posted Purchase print source differs from the saved revision")
    tables = (m.InvoiceSupplyFact, m.InvoiceComponentFact, m.InvoiceTaxComponent)
    groups: list[list[Any]] = []
    for model in tables:
        rows = list(
            await db.scalars(
                select(model)
                .where(
                    model.company_id == command.company_id,
                    model.invoice_id == record.id,
                )
                .order_by(model.id)
                .limit(1601)
            )
        )
        if len(rows) > 1600:
            raise ConflictError("posted Purchase exceeds print limits")
        for row in rows:
            require_fields(
                current,
                model.__tablename__,
                set(model.__table__.columns.keys())
                - {"created_at", "updated_at", "created_by", "updated_by", "tenant_id"},
                row=row,
            )
        groups.append(rows)
    supplies, components, taxes = groups
    calculation = InvoiceCalculationDetail.model_validate(
        {
            **{
                key: getattr(record, key)
                for key in fields
                if key in InvoiceCalculationDetail.model_fields
            },
            "lines": [
                {
                    "key": line.line_key,
                    **{
                        key: getattr(line, key)
                        for key in ("entered", "commercial", "taxable", "price_rounding", "payable")
                    },
                    "taxes": [
                        {
                            "key": tax.component_key,
                            "code": tax.code,
                            "basis": tax.basis,
                            "amount": tax.amount,
                            "supplier_charged": tax.supplier_charged,
                        }
                        for tax in taxes
                        if tax.supply_id == line.id
                    ],
                }
                for line in sorted(supplies, key=lambda row: row.sequence)
            ],
            "components": [
                {
                    "key": row.component_key,
                    **{
                        key: getattr(row, key)
                        for key in ("basis_amount", "basis_quantity", "input_amount", "amount")
                    },
                }
                for row in components
            ],
            "allocations": [],
            "tax_evidence": [],
        }
    )
    return PurchasePrintFacts(
        calculation=calculation,
        supplier_name=supplier_name,
        source="POSTED",
        voucher_number=await journal_number(db, current, record),
        lines=print_lines(
            body, {line.line_key: line.classification_code for line in supplies}, goods
        ),
        # Supply accounts are the posted record's own; settlement accounts come from the saved
        # bill, whose accepted calculation hash (which covers its tenders) was checked above.
        ledgers=await ledger_names(
            db,
            current,
            command.company_id,
            {line.line_key: line.account_id for line in supplies},
            settlement_targets,
        ),
    )
