"""Serialized statutory credit history through native journal posting."""

import datetime as dt
import uuid
from dataclasses import asdict, dataclass, fields
from decimal import Decimal
from fractions import Fraction

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import CommandResult
from billing_platform.ids import uuid7
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.invoice_credit import CreditEvent, CreditEvidence, CreditTerms, position
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.invoice import InvoiceRecord, InvoiceSupplyFact, InvoiceTaxComponent
from accounting.models.invoice_credit import InvoiceCreditAction, InvoiceCreditEvent
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import Account, AccountGroup, AccountHead
from accounting.models.subledger import OpenItem
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.schemas.invoice_credit import CreditActionRequest, InvoiceCreditPosition
from accounting.schemas.ledger import JournalCreate, JournalLineCreate
from accounting.tasks.finance_records import create_row, require_fields
from accounting.tasks.financial_commands import FinancialEffect, financial_command
from accounting.tasks.fiscal import posting_period
from accounting.tasks.invoice_mappings import tax_account
from accounting.tasks.journal_drafts import create_in_transaction, lines
from accounting.tasks.subledger_reads import item_balance
from accounting.tasks.voucher_tax import mapping_row


@dataclass(frozen=True)
class CreditSource:
    invoice: InvoiceRecord
    supply: InvoiceSupplyFact
    component: InvoiceTaxComponent
    journal: Journal
    actions: tuple[InvoiceCreditAction, ...]
    latest_event_id: uuid.UUID


def proof(body: CreditActionRequest | InvoiceCreditAction) -> CreditEvidence:
    return CreditEvidence(
        **{field.name: getattr(body, field.name) for field in fields(CreditEvidence)}
    )


def events(source: CreditSource) -> tuple[CreditEvent, ...]:
    assert source.supply.supplier_invoice_date is not None
    return (
        CreditEvent("RECORD", source.component.amount, source.supply.supplier_invoice_date),
        *(CreditEvent(row.kind, row.amount, row.event_date, proof(row)) for row in source.actions),
    )


def terms(source: CreditSource, annual: dt.date | None = None) -> CreditTerms:
    assert source.supply.supplier_invoice_date is not None
    dates = [row.annual_return_filed_on for row in source.actions if row.annual_return_filed_on]
    if annual:
        dates.append(annual)
    return CreditTerms(
        source.supply.supplier_invoice_date,
        source.supply.reverse_charge,
        source.supply.credit_state == "PENDING_EVIDENCE",
        min(dates) if dates else None,
    )


async def load(db: AsyncSession, access: Access, component_id: uuid.UUID) -> CreditSource:
    company = access.context.company_id
    component = await company_object(db, InvoiceTaxComponent, component_id, company_id=company)
    require_fields(
        access,
        "invoice_tax_component",
        {"invoice_id", "supply_id", "amount", "code", "supplier_charged"},
        row=component,
    )
    invoice = await company_object(db, InvoiceRecord, component.invoice_id, company_id=company)
    supply = await company_object(db, InvoiceSupplyFact, component.supply_id, company_id=company)
    require_fields(
        access,
        "invoice_record",
        {"kind", "intent_id", "currency", "payable", "party_account_id"},
        row=invoice,
    )
    require_fields(
        access,
        "invoice_supply_fact",
        {
            "supplier_invoice_date",
            "reverse_charge",
            "credit_state",
            "company_registration_id",
            "source_evidence",
        },
        row=supply,
    )
    intent = await company_object(db, VoucherMoneyIntent, invoice.intent_id, company_id=company)
    if intent.journal_id is None:
        raise ConflictError("purchase has no committed journal")
    journal = await company_object(db, Journal, intent.journal_id, company_id=company)
    require_fields(access, "journal", {"status", "posting_date"}, row=journal)
    if (
        journal.status != "POSTED"
        or invoice.kind != "PURCHASE"
        or supply.supplier_invoice_date is None
        or supply.company_registration_id is None
        or component.amount <= 0
    ):
        raise ConflictError("input credit requires a posted purchase tax component")
    require_fields(access, "invoice_credit_event", {"action_id", "invoice_id"})
    require_fields(
        access,
        "invoice_credit_action",
        set(CreditActionRequest.model_fields) | {"journal_id", "currency"},
    )
    rows = list(
        (
            await db.execute(
                select(InvoiceCreditAction, InvoiceCreditEvent.id)
                .join(
                    InvoiceCreditEvent,
                    (InvoiceCreditEvent.action_id == InvoiceCreditAction.id)
                    & (InvoiceCreditEvent.company_id == InvoiceCreditAction.company_id),
                )
                .where(
                    InvoiceCreditAction.company_id == company,
                    InvoiceCreditAction.component_id == component.id,
                )
                .order_by(InvoiceCreditEvent.id)
                .limit(1000)
            )
        ).all()
    )
    if len(rows) >= 1000:
        raise ConflictError("credit component history exceeds supported capacity")
    return CreditSource(
        invoice,
        supply,
        component,
        journal,
        tuple(row[0] for row in rows),
        rows[-1][1] if rows else component.id,
    )


async def read_position(
    db: AsyncSession, access: Access, component_id: uuid.UUID
) -> InvoiceCreditPosition:
    source = await load(db, access, component_id)
    return InvoiceCreditPosition(
        component_id=component_id,
        latest_event_id=source.latest_event_id,
        currency=source.invoice.currency,
        **asdict(position(terms(source), events(source))),
    )


async def unpaid(db: AsyncSession, access: Access, source: CreditSource, on: dt.date) -> Fraction:
    require_fields(access, "open_item", {"journal_line_id", "direction", "account_id"})
    items = list(
        await db.scalars(
            select(OpenItem)
            .join(
                JournalLine,
                (JournalLine.id == OpenItem.journal_line_id)
                & (JournalLine.company_id == OpenItem.company_id),
            )
            .where(
                OpenItem.company_id == source.invoice.company_id,
                JournalLine.journal_id == source.journal.id,
                OpenItem.account_id == source.invoice.party_account_id,
                OpenItem.direction == "DEBT",
            )
            .limit(201)
        )
    )
    if not items or len(items) > 200:
        raise ConflictError("purchase bill settlement evidence is incomplete")
    result = Fraction()
    for item in items:
        result += Fraction((await item_balance(db, access, item.id, on)).remaining)
    return result


async def validate(
    db: AsyncSession, access: Access, source: CreditSource, body: CreditActionRequest
) -> None:
    access.actor.require_scope(
        "accounting.tax.manage", target=ScopePath(company_id=access.context.company_id)
    )
    if body.expected_event_id != source.latest_event_id:
        raise ConflictError("input-credit history changed; reload before retrying")
    if body.posting_date < body.event_date or body.posting_date < source.journal.posting_date:
        raise ValidationFailedError(
            "tax action posting cannot precede its evidence or source posting"
        )
    if body.annual_return_filed_on and body.annual_return_filed_on > body.event_date:
        raise ValidationFailedError("annual return evidence cannot be future dated")
    await posting_period(db, access, body.posting_date)
    current = position(terms(source), events(source))
    position(
        terms(source, body.annual_return_filed_on),
        (*events(source), CreditEvent(body.kind, body.amount, body.event_date, proof(body))),
    )
    if body.supplier_paid or body.kind == "REVERSE_PAYMENT":
        outstanding = await unpaid(db, access, source, body.event_date)
        if body.supplier_paid and outstanding:
            raise ConflictError("supplier-paid evidence differs from recorded bill settlements")
        if body.kind == "REVERSE_PAYMENT" and (
            Fraction(body.amount) + Fraction(current.suspended)
            > Fraction(source.component.amount) * outstanding / Fraction(source.invoice.payable)
        ):
            raise ValidationFailedError("payment-related reversal exceeds proportionate unpaid tax")
    if body.kind != "BLOCK" and body.offset_account_id is not None:
        raise ValidationFailedError("only blocked credit selects an expense offset")
    if body.kind != "RCM_DISCHARGE" and body.cash_deposit_line_id is not None:
        raise ValidationFailedError("cash-offset evidence belongs only to RCM discharge")


async def original_account(
    db: AsyncSession, access: Access, source: CreditSource, purpose: str
) -> uuid.UUID:
    key = purpose + "_" + source.component.code
    found = [
        row
        for row in source.supply.source_evidence.get("posting_mappings", [])
        if row["purpose"] == key and row["ready"]
    ]
    if len(found) != 1:
        raise ConflictError("purchase has no unique original tax posting account")
    account_id = uuid.UUID(found[0]["account_id"])
    await tax_account(
        db,
        access,
        account_id,
        purpose=purpose,
        code=source.component.code,
        registration_id=str(source.supply.company_registration_id),
        currency=source.invoice.currency,
    )
    return account_id


async def input_account(
    db: AsyncSession, access: Access, source: CreditSource, on: dt.date
) -> uuid.UUID:
    # All claims for a source component retain the first claimed input account. A later
    # mapping change cannot redirect a reversal away from the account originally debited.
    first = next((row for row in source.actions if row.kind == "CLAIM"), None)
    if first and first.journal_id:
        native = await lines(db, source.invoice.company_id, first.journal_id)
        account_id = next(row.account_id for row in native if row.side == "DEBIT")
    else:
        mapping = await mapping_row(
            db,
            access,
            "INPUT_" + source.component.code,
            str(source.supply.company_registration_id),
            on,
        )
        if mapping is None:
            raise ConflictError("eligible input tax mapping is missing or ambiguous")
        account_id = mapping.account_id
    await tax_account(
        db,
        access,
        account_id,
        purpose="INPUT",
        code=source.component.code,
        registration_id=str(source.supply.company_registration_id),
        currency=source.invoice.currency,
    )
    return account_id


async def cash_offset(
    db: AsyncSession, access: Access, source: CreditSource, body: CreditActionRequest
) -> uuid.UUID:
    if body.cash_deposit_line_id is None:
        raise ValidationFailedError("RCM discharge requires the posted statutory cash deposit line")
    line = await company_object(
        db, JournalLine, body.cash_deposit_line_id, company_id=source.invoice.company_id
    )
    require_fields(
        access, "journal_line", {"journal_id", "account_id", "side", "amount", "currency"}, row=line
    )
    journal = await company_object(db, Journal, line.journal_id, company_id=line.company_id)
    require_fields(access, "journal", {"status", "posting_date", "kind"}, row=journal)
    if (
        journal.status != "POSTED"
        or journal.kind in {"REVERSAL", "TAX_ACTION"}
        or journal.posting_date > body.event_date
        or line.side != "DEBIT"
        or line.currency != source.invoice.currency
    ):
        raise ValidationFailedError("statutory cash deposit must precede its RCM offset")
    await tax_account(
        db,
        access,
        line.account_id,
        purpose="DEPOSIT",
        code=source.component.code,
        registration_id=str(source.supply.company_registration_id),
        currency=source.invoice.currency,
    )
    # Verify a cash/bank-funded deposit, rather than a transfer from eligible credit.
    siblings = await lines(db, line.company_id, journal.id)
    credited = [row for row in siblings if row.side == "CREDIT"]
    for sibling in credited:
        account = await company_object(db, Account, sibling.account_id, company_id=line.company_id)
        require_fields(access, "account", {"kind"}, row=account)
        if account.kind not in {"CASH", "BANK"}:
            raise ValidationFailedError("RCM cannot be discharged using input credit")
    reversed_id = await db.scalar(
        select(Journal.id)
        .where(
            Journal.company_id == line.company_id,
            Journal.reversal_of_id == journal.id,
            Journal.status == "POSTED",
        )
        .limit(1)
    )
    if reversed_id:
        raise ConflictError("statutory cash deposit has been reversed")
    used = list(
        await db.scalars(
            select(InvoiceCreditAction.amount)
            .join(
                InvoiceCreditEvent,
                (InvoiceCreditEvent.action_id == InvoiceCreditAction.id)
                & (InvoiceCreditEvent.company_id == InvoiceCreditAction.company_id),
            )
            .where(
                InvoiceCreditAction.company_id == line.company_id,
                InvoiceCreditAction.cash_deposit_line_id == line.id,
            )
            .limit(1001)
        )
    )
    if len(used) > 1000 or sum(map(Fraction, used), Fraction()) + Fraction(body.amount) > Fraction(
        line.amount
    ):
        raise ConflictError("RCM offset exceeds the remaining statutory cash deposit")
    return line.account_id


async def distribution(
    db: AsyncSession, access: Access, source: CreditSource, body: CreditActionRequest
) -> list[JournalLineCreate]:
    if body.kind == "VERIFY":
        return []
    if body.kind == "RCM_DISCHARGE":
        if source.supply.tax_point_date is None or body.event_date < source.supply.tax_point_date:
            raise ValidationFailedError("RCM discharge cannot precede its liability tax point")
        debit = await original_account(db, access, source, "RCM")
        credit = await cash_offset(db, access, source, body)
    else:
        pending = await original_account(db, access, source, "PENDING")
        if body.kind == "BLOCK":
            if body.offset_account_id is None:
                raise ValidationFailedError("blocked credit requires an expense account")
            account = await company_object(
                db, Account, body.offset_account_id, company_id=source.invoice.company_id
            )
            require_fields(
                access, "account", {"kind", "status", "posting_policy", "group_id"}, row=account
            )
            group = await company_object(
                db, AccountGroup, account.group_id, company_id=account.company_id
            )
            require_fields(access, "account_group", {"head_id", "status"}, row=group)
            head = await company_object(db, AccountHead, group.head_id, company_id=group.company_id)
            require_fields(access, "account_head", {"nature"}, row=head)
            if (
                account.kind != "GENERAL"
                or account.status != "ACTIVE"
                or account.posting_policy != "MANUAL_ALLOWED"
                or group.status != "ACTIVE"
                or head.nature != "EXPENSE"
            ):
                raise ValidationFailedError(
                    "blocked service credit requires an active expense account"
                )
            debit, credit = account.id, pending
        else:
            eligible = await input_account(db, access, source, body.event_date)
            debit, credit = (
                (pending, eligible) if body.kind == "REVERSE_PAYMENT" else (eligible, pending)
            )
    if debit == credit:
        raise ValidationFailedError("tax movement requires distinct posting accounts")
    return [
        JournalLineCreate(
            account_id=debit,
            side="DEBIT",
            currency=source.invoice.currency,
            amount=body.amount,
            exchange_rate=Decimal(1),
        ),
        JournalLineCreate(
            account_id=credit,
            side="CREDIT",
            currency=source.invoice.currency,
            amount=body.amount,
            exchange_rate=Decimal(1),
        ),
    ]


async def create(
    factory: async_sessionmaker[AsyncSession], access: Access, body: CreditActionRequest, key: str
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        source = await load(db, access, body.component_id)
        await validate(db, access, source, body)
        entries = await distribution(db, access, source, body)
        journal = (
            await create_in_transaction(
                db,
                access,
                JournalCreate(
                    document_date=body.event_date,
                    posting_date=body.posting_date,
                    description=body.reason,
                    lines=entries,
                ),
                kind="TAX_ACTION",
                source_system="accounting",
                source_type="invoice_credit",
                source_id=str(uuid7()),
            )
            if entries
            else None
        )
        action = await create_row(
            db,
            access,
            "invoice_credit_action",
            **body.model_dump(),
            invoice_id=source.invoice.id,
            currency=source.invoice.currency,
            journal_id=journal.id if journal else None,
        )
        if journal is None:
            await create_row(
                db,
                access,
                "invoice_credit_event",
                invoice_id=source.invoice.id,
                action_id=action.id,
            )
        return FinancialEffect(action, permission="accounting.tax.manage")

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["invoice_credit_action"],
        "create",
        body,
        key,
        mutate,
        permission="ledger.post_journal",
        status=201,
    )


async def for_journal(db: AsyncSession, journal: Journal) -> InvoiceCreditAction:
    action = await db.scalar(
        select(InvoiceCreditAction).where(
            InvoiceCreditAction.company_id == journal.company_id,
            InvoiceCreditAction.journal_id == journal.id,
        )
    )
    if action is None:
        raise ConflictError("tax action has no native credit instruction")
    return action


async def before_post(db: AsyncSession, access: Access, journal: Journal) -> None:
    action = await for_journal(db, journal)
    body = CreditActionRequest.model_validate(
        {key: getattr(action, key) for key in CreditActionRequest.model_fields}
    )
    source = await load(db, access, body.component_id)
    await validate(db, access, source, body)
    expected = await distribution(db, access, source, body)
    native = await lines(db, journal.company_id, journal.id)
    if len(expected) != len(native) or any(
        (a.account_id, a.side, a.currency, a.amount, a.exchange_rate)
        != (b.account_id, b.side, b.currency, b.amount, b.exchange_rate)
        for a, b in zip(expected, native, strict=True)
    ):
        raise ConflictError("tax posting differs from its current native instruction")


async def after_post(db: AsyncSession, access: Access, journal: Journal) -> None:
    action = await for_journal(db, journal)
    await create_row(
        db, access, "invoice_credit_event", invoice_id=action.invoice_id, action_id=action.id
    )


async def reversal_guard(db: AsyncSession, original: Journal) -> None:
    if original.kind == "TAX_ACTION":
        raise ConflictError("tax credit journals require a linked statutory correction")
    dependent = await db.scalar(
        select(InvoiceCreditEvent.id)
        .join(InvoiceCreditAction, InvoiceCreditAction.id == InvoiceCreditEvent.action_id)
        .join(JournalLine, JournalLine.id == InvoiceCreditAction.cash_deposit_line_id)
        .where(
            InvoiceCreditEvent.company_id == original.company_id,
            InvoiceCreditAction.company_id == original.company_id,
            JournalLine.company_id == original.company_id,
            JournalLine.journal_id == original.id,
        )
        .limit(1)
    )
    if dependent:
        raise ConflictError("statutory cash deposit has committed RCM offsets")
