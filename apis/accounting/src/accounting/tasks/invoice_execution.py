"""Compose service/account invoice effects through the existing money execution protocol."""

import uuid
from decimal import Decimal
from fractions import Fraction
from typing import Any, Literal

from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.contracts import ExecutionCommand
from voucher_execution.invoice import InvoiceCalculationDetail, InvoiceInput, InvoicePreviewCommand
from voucher_execution.money import (
    AccountEntry,
    BillAllocation,
    MoneyInput,
    MoneyPolicy,
    validate_money_controls,
)
from voucher_execution.stock_facts import StockFenceFacts

from accounting.api.auth import Access
from accounting.domain.invoice_calculation import money
from accounting.models.invoice import (
    InvoiceComponentFact,
    InvoicePostingLine,
    InvoiceRecord,
    InvoiceSupplyFact,
    InvoiceTaxComponent,
)
from accounting.models.ledger import Journal
from accounting.models.subledger import OpenItem
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.tasks.invoice_calculation import preview
from accounting.tasks.invoice_goods import GoodsFacts
from accounting.tasks.invoice_goods import facts_for as goods_facts

KINDS = frozenset({"SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"})


def request_for(command: ExecutionCommand) -> InvoicePreviewCommand:
    source = command.source_payload
    if command.kind not in KINDS or command.profile != "STANDARD" or command.purpose != "POST":
        raise ValidationFailedError("invoice requires a supported posting profile")
    if (
        source.get("mode") != "ACCOUNTS"
        or source.get("lines")
        or source.get("stock_date")
        or command.stock_date
    ):
        raise ValidationFailedError("this invoice profile cannot post stock or common item lines")
    if source.get("financial") is not None or str(source.get("posting_date")) != str(
        command.posting_date
    ):
        raise ValidationFailedError(
            "invoice requires its own accepted distribution and posting date"
        )
    policy = (command.configuration_evidence or {}).get("policy", {})
    if not isinstance(policy, dict) or not isinstance(policy.get("invoice"), dict):
        raise ValidationFailedError("invoice execution requires explicit native configuration")
    try:
        request = InvoicePreviewCommand.model_validate(
            {
                "tenant_id": command.tenant_id,
                "company_id": command.company_id,
                "actor_user_id": command.actor_user_id,
                "authority": command.authority,
                "kind": command.kind,
                "profile": command.profile,
                "currency": source.get("currency"),
                "document_date": source.get("document_date"),
                "posting_date": command.posting_date,
                "invoice": source.get("invoice"),
                "policy": policy["invoice"],
                "configuration_hash": command.configuration_hash,
                "company_configuration_hash": command.company_configuration_hash,
            }
        )
    except ValueError as error:
        raise ValidationFailedError("invalid invoice execution contract") from error
    if any(line.supply_kind == "GOODS" or line.item_line_key for line in request.invoice.supplies):
        raise ValidationFailedError("goods invoice execution requires the stock phase")
    if (command.kind in {"CREDIT_NOTE", "DEBIT_NOTE"}) != (
        request.invoice.source_invoice_id is not None
    ):
        raise ValidationFailedError("financial notes require an original invoice source")
    return request


def settlement_key(body: InvoiceInput) -> uuid.UUID:
    return uuid.uuid5(body.party_line_key, "invoice-settlement")


def allocations(body: InvoiceInput, kind: str) -> tuple[BillAllocation, ...]:
    for allocation in body.allocations:
        if body.party_line_key not in {allocation.debt.line_key, allocation.credit.line_key}:
            raise ValidationFailedError(
                "invoice adjustments must reference this invoice's party bill"
            )
    result = list(body.allocations)
    if body.tenders:
        invoice_target = {"line_key": body.party_line_key}
        settlement_target = {"line_key": settlement_key(body)}
        result.append(
            BillAllocation.model_validate(
                {
                    "allocation_key": uuid.uuid5(
                        body.party_line_key, "invoice-settlement-allocation"
                    ),
                    "debt": (
                        invoice_target if kind in {"SALES", "PURCHASE"} else settlement_target
                    ),
                    "credit": (
                        settlement_target if kind in {"SALES", "PURCHASE"} else invoice_target
                    ),
                    "currency": body.tenders[0].tender.currency,
                    "amount": money(
                        sum((Fraction(row.tender.amount) for row in body.tenders), Fraction()), 4
                    ),
                }
            )
        )
    return tuple(result)


async def claimed(
    db: AsyncSession,
    company_id: uuid.UUID,
    source_id: uuid.UUID,
    *,
    exclude: uuid.UUID | None = None,
) -> dict[uuid.UUID, Decimal]:
    """Commercial amounts already claimed per original supply line by prepared/committed notes."""
    statement = (
        select(InvoiceSupplyFact.line_key, InvoiceSupplyFact.commercial)
        .join(
            InvoiceRecord,
            (InvoiceRecord.company_id == InvoiceSupplyFact.company_id)
            & (InvoiceRecord.id == InvoiceSupplyFact.invoice_id),
        )
        .join(
            VoucherMoneyIntent,
            (VoucherMoneyIntent.company_id == InvoiceRecord.company_id)
            & (VoucherMoneyIntent.id == InvoiceRecord.intent_id),
        )
        .where(
            InvoiceRecord.company_id == company_id,
            InvoiceRecord.source_invoice_id == source_id,
            VoucherMoneyIntent.status.in_(["PREPARED", "COMMITTED"]),
        )
        .limit(1001)
    )
    if exclude is not None:
        statement = statement.where(VoucherMoneyIntent.execution_id != exclude)
    claims = list(await db.execute(statement))
    if len(claims) > 1000:
        raise ConflictError("original invoice has too many financial return claims")
    consumed: dict[uuid.UUID, Decimal] = {}
    for key, amount in claims:
        consumed[key] = consumed.get(key, Decimal(0)) + amount
    return consumed


async def committed_source(
    db: AsyncSession, company_id: uuid.UUID, source: InvoiceRecord
) -> bool:
    """The original invoice's execution committed and its journal is posted."""
    intent = await db.scalar(
        select(VoucherMoneyIntent).where(
            VoucherMoneyIntent.company_id == company_id,
            VoucherMoneyIntent.id == source.intent_id,
        )
    )
    journal = (
        await db.scalar(
            select(Journal).where(Journal.company_id == company_id, Journal.id == intent.journal_id)
        )
        if intent and intent.journal_id
        else None
    )
    return bool(
        intent is not None
        and intent.status == "COMMITTED"
        and journal is not None
        and journal.status == "POSTED"
    )


async def validate_note_source(
    db: AsyncSession,
    request: InvoicePreviewCommand,
    calculation: InvoiceCalculationDetail,
    execution_id: uuid.UUID,
) -> None:
    """Reserve a simple untaxed return against immutable original supply amounts."""
    body = request.invoice
    source_id = body.source_invoice_id
    if source_id is None:
        raise ValidationFailedError("financial note requires an original invoice")
    source = await db.scalar(
        select(InvoiceRecord)
        .where(InvoiceRecord.company_id == request.company_id, InvoiceRecord.id == source_id)
        .with_for_update()
    )
    original_kind = "SALES" if request.kind == "CREDIT_NOTE" else "PURCHASE"
    if (
        source is None
        or source.kind != original_kind
        or source.currency != request.currency
        or source.party_account_id != body.party_account_id
        or source.posting_date > request.posting_date
    ):
        raise ConflictError("financial note has no compatible original invoice")
    if not await committed_source(db, request.company_id, source):
        raise ConflictError("original invoice is not committed")
    if (
        body.tax.profile != "UNTAXED_ACCOUNT"
        or any(line.tax and line.tax.profile != "UNTAXED_ACCOUNT" for line in body.supplies)
        or any(line.free_purpose != "NONE" for line in body.supplies)
        or body.components
        or body.rounding_increment is not None
        or body.supplier_declared_total is not None
        or calculation.tax_total
        or calculation.rounding
        or source.tax_total
        or source.rounding
    ):
        raise ConflictError("financial note requires an untaxed source without adjustments")
    for model in (InvoiceComponentFact, InvoiceTaxComponent):
        if await db.scalar(
            select(model.id)
            .where(model.company_id == request.company_id, model.invoice_id == source.id)
            .limit(1)
        ):
            raise ConflictError("original components require source-component return claims")
    source_party_line = await db.scalar(
        select(InvoicePostingLine.journal_line_id)
        .where(
            InvoicePostingLine.company_id == request.company_id,
            InvoicePostingLine.invoice_id == source.id,
            InvoicePostingLine.tracking == "NEW_REF",
        )
        .limit(1)
    )
    source_bill = (
        await db.scalar(
            select(OpenItem).where(
                OpenItem.company_id == request.company_id,
                OpenItem.journal_line_id == source_party_line,
            )
        )
        if source_party_line is not None
        else None
    )
    if source_bill is None or source_bill.reversal_journal_id is not None:
        raise ConflictError("original invoice party bill is missing")
    for allocation in body.allocations:
        source_target, note_target = allocation.debt, allocation.credit
        if (
            source_target.item_id != source_bill.id
            or source_target.line_key is not None
            or note_target.line_key != body.party_line_key
            or note_target.item_id is not None
            or allocation.currency != request.currency
            or allocation.fx_account_id is not None
        ):
            raise ConflictError("financial note can adjust only its original party bill")
    settled = sum(
        (Fraction(row.tender.amount) for row in body.tenders), Fraction()
    ) + sum((Fraction(row.amount) for row in body.allocations), Fraction())
    if settled > Fraction(calculation.payable):
        raise ConflictError("financial note settlement exceeds its payable amount")
    original = {
        line.line_key: line
        for line in await db.scalars(
            select(InvoiceSupplyFact).where(
                InvoiceSupplyFact.company_id == request.company_id,
                InvoiceSupplyFact.invoice_id == source.id,
            )
        )
    }
    consumed = await claimed(db, request.company_id, source.id, exclude=execution_id)
    for line in calculation.lines:
        source_line = original.get(line.key)
        note_line = next((item for item in body.supplies if item.line_key == line.key), None)
        if (
            source_line is None
            or note_line is None
            or note_line.account_id != source_line.account_id
            or note_line.supply_kind != source_line.supply_kind
            or source_line.tax_profile != "UNTAXED_ACCOUNT"
            or line.commercial <= 0
            or line.commercial > source_line.commercial - consumed.get(line.key, Decimal(0))
        ):
            raise ConflictError("financial note exceeds the original supply entitlement")


def goods_request_for(command: ExecutionCommand) -> InvoicePreviewCommand:
    """The accepted goods Purchase bill (B24) behind a stock-and-invoice execution."""
    source = command.source_payload
    stock = source.get("stock")
    if (
        command.kind != "PURCHASE"
        or command.profile != "STANDARD"
        or command.purpose != "POST"
        or not isinstance(stock, dict)
        or stock.get("action") != "PURCHASE_INVOICE"
        or source.get("mode") not in {"ITEMS", "MIXED"}
        or source.get("financial") is not None
        or str(source.get("posting_date")) != str(command.posting_date)
        or command.stock_date != command.posting_date
    ):
        raise ValidationFailedError("a goods bill posts its accepted stock and invoice together")
    policy = (command.configuration_evidence or {}).get("policy", {})
    if not isinstance(policy, dict) or not isinstance(policy.get("invoice"), dict):
        raise ValidationFailedError("invoice execution requires explicit native configuration")
    try:
        return InvoicePreviewCommand.model_validate(
            {
                "tenant_id": command.tenant_id,
                "company_id": command.company_id,
                "actor_user_id": command.actor_user_id,
                "authority": command.authority,
                "kind": command.kind,
                "profile": command.profile,
                "currency": source.get("currency"),
                "document_date": source.get("document_date"),
                "posting_date": command.posting_date,
                "invoice": source.get("invoice"),
                "policy": policy["invoice"],
                "configuration_hash": command.configuration_hash,
                "company_configuration_hash": command.company_configuration_hash,
                "stock": stock,
            }
        )
    except ValueError as error:
        raise ValidationFailedError("invalid goods bill execution contract") from error


async def resolve(
    db: AsyncSession, access: Access, command: ExecutionCommand
) -> tuple[InvoicePreviewCommand, InvoiceCalculationDetail, MoneyInput, MoneyPolicy]:
    return await _compose(db, access, command, request_for(command), None)


async def resolve_goods(
    db: AsyncSession, access: Access, command: ExecutionCommand, facts: StockFenceFacts
) -> tuple[InvoicePreviewCommand, InvoiceCalculationDetail, MoneyInput, MoneyPolicy]:
    """A goods bill's distribution: each goods line debits inventory at its landed cost.

    ``facts`` are the execution's own signed Catalog facts, so the bill is costed from the same
    item evidence its stock movements are validated against.
    """
    request = goods_request_for(command)
    return await _compose(db, access, command, request, goods_facts(request, facts))


async def _compose(
    db: AsyncSession,
    access: Access,
    command: ExecutionCommand,
    request: InvoicePreviewCommand,
    goods: GoodsFacts | None,
) -> tuple[InvoicePreviewCommand, InvoiceCalculationDetail, MoneyInput, MoneyPolicy]:
    body = request.invoice
    calculation = await preview(db, access, request, posting=True, goods=goods)
    if (
        body.accepted_calculation_hash is None
        or body.accepted_calculation_hash != calculation.calculation_hash
    ):
        raise ConflictError("the invoice calculation changed or has not been accepted")
    if calculation.payable <= 0:
        raise ValidationFailedError("invoice must have positive consideration")
    if command.kind in {"CREDIT_NOTE", "DEBIT_NOTE"}:
        await validate_note_source(db, request, calculation, command.execution_id)
    if any(
        component.cost_targets or component.commercial_treatment != "COUNTERPARTY"
        for component in body.components
    ):
        raise ValidationFailedError("account invoices cannot capitalize third-party stock costs")
    side: Literal["DEBIT", "CREDIT"] = (
        "CREDIT" if command.kind in {"SALES", "DEBIT_NOTE"} else "DEBIT"
    )
    opposite: Literal["DEBIT", "CREDIT"] = "DEBIT" if side == "CREDIT" else "CREDIT"
    entries: list[AccountEntry] = []

    def add(
        key: uuid.UUID,
        account_id: uuid.UUID,
        version: int,
        amount: Decimal,
        direction: str = side,
        **extra: Any,
    ) -> None:
        if not amount:
            return
        if amount < 0:
            direction = "DEBIT" if direction == "CREDIT" else "CREDIT"
            amount = amount.copy_abs()
        entries.append(
            AccountEntry.model_validate(
                {
                    "line_key": key,
                    "account_id": account_id,
                    "source_version": version,
                    "side": direction,
                    "currency": request.currency,
                    "amount": amount,
                    "exchange_rate": body.exchange_rate,
                    **extra,
                }
            )
        )

    add(
        body.party_line_key,
        body.party_account_id,
        body.party_account_version,
        calculation.payable,
        opposite,
        tracking="NEW_REF",
        bill_reference=body.bill_reference,
        due_date=body.due_date,
    )
    source_components = {row.component_key: row for row in body.components}
    result_components = {row.key: row for row in calculation.components}
    supplied = {row.line_key: row for row in body.supplies}
    evidence: dict[str, Any] = {str(row["line_key"]): row for row in calculation.tax_evidence}
    for line in calculation.lines:
        source = supplied[line.key]
        # A goods line debits inventory at its landed cost, which already holds its share of
        # charges and any GST that cannot be claimed (D02, 2026-11-03).
        goods_line = source.supply_kind == "GOODS"
        if goods_line and line.stock_cost is None:
            raise ConflictError("a goods line requires its calculated landed cost")
        separately_posted = sum(
            (
                Fraction(share.amount)
                for share in calculation.allocations
                if share.line_key == line.key
                and share.purpose == "COMMERCIAL"
                and source_components[share.component_key].account_id
            ),
            Fraction(),
        )
        add(
            line.key,
            source.account_id,
            source.account_version,
            line.stock_cost
            if goods_line and line.stock_cost is not None
            else money(Fraction(line.commercial) - separately_posted, 4),
            description=source.description[:500],
        )
        proof = evidence[str(line.key)]
        for tax in line.taxes:
            purposes = [("OUTPUT_" + tax.code, side)] if command.kind == "SALES" else []
            if command.kind == "PURCHASE":
                if proof["credit_state"] == "PENDING_EVIDENCE":
                    purposes.append(("PENDING_" + tax.code, side))
                elif not goods_line:
                    add(
                        uuid.uuid5(line.key, "nonrecoverable:" + tax.key),
                        source.account_id,
                        source.account_version,
                        tax.amount,
                    )
                if not tax.supplier_charged:
                    purposes.append(("RCM_" + tax.code, opposite))
            for purpose, direction in purposes:
                mapping = next(
                    (row for row in proof["posting_mappings"] if row["purpose"] == purpose), None
                )
                if mapping is None or not mapping["ready"]:
                    raise ValidationFailedError("tax posting mapping is missing or ambiguous")
                add(
                    uuid.uuid5(line.key, purpose + ":" + tax.key),
                    uuid.UUID(mapping["account_id"]),
                    mapping["account_version"],
                    tax.amount,
                    direction,
                )
    for key, component in source_components.items():
        if component.account_id is not None:
            assert component.account_version is not None
            add(key, component.account_id, component.account_version, result_components[key].amount)
    if calculation.rounding:
        if body.rounding_account_id is None or body.rounding_account_version is None:
            raise ValidationFailedError(
                "calculated price/invoice rounding requires its posting account"
            )
        add(
            uuid.uuid5(body.party_line_key, "invoice-rounding"),
            body.rounding_account_id,
            body.rounding_account_version,
            calculation.rounding,
        )
    settlement = sum((Fraction(row.tender.amount) for row in body.tenders), Fraction())
    if settlement:
        add(
            settlement_key(body),
            body.party_account_id,
            body.party_account_version,
            money(settlement, 4),
            side,
            tracking="ON_ACCOUNT",
            bill_reference=body.bill_reference,
        )
    for key in sorted({row.tender.line_key for row in body.tenders}, key=str):
        selected = [row for row in body.tenders if row.tender.line_key == key]
        if len({(row.account_id, row.account_version) for row in selected}) != 1:
            raise ValidationFailedError("split settlement lines require the same account version")
        add(
            key,
            selected[0].account_id,
            selected[0].account_version,
            money(sum((Fraction(row.tender.amount) for row in selected), Fraction()), 4),
            opposite,
        )
    try:
        financial = MoneyInput(
            accounts=tuple(entries),
            tenders=tuple(row.tender for row in body.tenders),
            allocations=allocations(body, command.kind),
        )
        policy = MoneyPolicy.model_validate(
            (command.configuration_evidence or {})["policy"].get("financial") or {}
        )
        validate_money_controls(financial, policy, posting_date=command.posting_date)
    except ValueError as error:
        raise ValidationFailedError("invoice distribution violates financial controls") from error
    return request, calculation, financial, policy
