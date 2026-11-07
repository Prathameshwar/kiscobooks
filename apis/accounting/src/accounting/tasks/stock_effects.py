"""Compile typed physical effects and their exact clearing-account distribution."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.exact import exact_decimal
from billing_platform.money import MoneyError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from voucher_execution import ExecutionCommand
from voucher_execution.money import AccountEntry, MoneyInput
from voucher_execution.stock import STOCK_PROFILES as PROFILES
from voucher_execution.stock import StockInput, StockPolicy
from voucher_execution.stock_facts import StockFenceFacts, StockItemFact, StockWarehouseFact

from accounting.api.auth import Access
from accounting.domain.stock_opening import calculate as calculate_opening
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import Account
from accounting.models.stock import (
    StockAccountPolicy,
    StockOpeningBridge,
    StockPosting,
)
from accounting.models.stock_tracking import StockLot
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.stock_resources import STOCK_MOVEMENT, STOCK_POSTING
from accounting.tasks.access import writable
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.stock_claims import customer_return, supplier_return
from accounting.tasks.stock_definitions import assert_retained
from accounting.tasks.stock_ledger import ZERO, Leg, StockLedger
from accounting.tasks.stock_opening_claims import claimed as opening_claimed
from accounting.tasks.stock_policy import effective
from accounting.tasks.stock_quote import FLAG, semantic_effects, semantic_hash
from accounting.tasks.stock_transfers import dispatch as transfer_dispatch
from accounting.tasks.stock_transfers import receive as transfer_receive
from accounting.tasks.voucher_money_effects import values

OPERATIONS = {
    "OPENING": "OPENING_STOCK",
    "RECEIPT": "PURCHASE_RECEIPT",
    "DISPATCH": "SALE_ISSUE",
    "TRANSFER": "TRANSFER_OUT",
    "TRANSFER_DISPATCH": "TRANSFER_OUT",
    "TRANSFER_RECEIPT": "TRANSFER_IN",
    "CUSTOMER_RETURN": "CUSTOMER_RETURN_RECEIPT",
    "SUPPLIER_RETURN": "SUPPLIER_RETURN_ISSUE",
    "COUNT": "ADJUSTMENT",
    "PURCHASE_INVOICE": "PURCHASE_RECEIPT",
}


@dataclass(frozen=True)
class StockEffects:
    posting_id: uuid.UUID
    movements: tuple[Leg, ...]
    money: MoneyInput | None
    features: frozenset[str]
    semantic: dict[str, Any]
    semantic_hash: str


def actual_tracking_features(
    ledger: StockLedger, current: Access, features: frozenset[str],
) -> frozenset[str]:
    if any(
        isinstance(row, StockLot) and row.expires_on is not None
        for row, _ in ledger.observed.values()
    ):
        if "expiry_tracking" not in current.context.features:
            raise ConflictError("company expiry tracking is required by the selected batches")
        return features | {"expiry_tracking"}
    return features


def captured(command: ExecutionCommand) -> tuple[StockInput, StockPolicy]:
    source = command.source_payload
    try:
        body = StockInput.model_validate(source.get("stock"))
        evidence = (command.configuration_evidence or {}).get("policy")
        billing = body.action == "PURCHASE_INVOICE"
        if not isinstance(evidence, dict) or (
            not isinstance(evidence.get("invoice"), dict)
            if billing
            else evidence.get("stock") is None
        ):
            raise ValueError("explicit native stock configuration is required")
        # A goods Purchase bill (B24) is configured by its invoice rules; it has no stock rules.
        policy = StockPolicy.model_validate(evidence.get("stock") or {})
    except (ValueError, ValidationError) as exc:
        raise ValidationFailedError("invalid native stock capture or configuration") from exc
    if (
        (command.kind, command.profile) != PROFILES[body.action]
        or command.stock_date is None
        or command.posting_date is None
        or source.get("mode") not in ({"ITEMS", "MIXED"} if billing else {"ITEMS"})
        or source.get("financial") is not None
        or (source.get("invoice") is not None) != billing
        or source.get("statutory_date")
    ):
        raise ValidationFailedError("stock requires its supported native physical-only profile")
    if command.purpose == "POST" and (
        str(source.get("posting_date")) != str(command.posting_date)
        or str(source.get("stock_date")) != str(command.stock_date)
        or body.stock_date != command.stock_date
    ):
        raise ValidationFailedError(
            "stock and posting dates must match the accepted voucher revision"
        )
    if source.get("currency") != body.currency:
        raise ValidationFailedError("stock currency differs from the voucher")
    if (
        body.action == "OPENING"
        and policy.opening_gl_mode != "EITHER"
        and body.opening_mode != policy.opening_gl_mode
    ):
        raise ValidationFailedError(
            "opening GL mode is restricted by the native voucher configuration"
        )
    if not policy.allow_zero_value_receipts and any(
        line.received_value == 0 for line in body.lines
    ):
        raise ValidationFailedError(
            "explicit zero-cost receipts are disabled by this voucher configuration"
        )
    return body, policy


def source_scope(
    current: Access,
    command: ExecutionCommand,
    body: StockInput,
    facts: StockFenceFacts,
    *,
    preview: bool = False,
) -> frozenset[str]:
    finance = financial_context(current)
    if facts.purpose != ("PREVIEW" if preview else "EXECUTION"):
        raise ConflictError("stock preview evidence cannot authorize physical posting")
    if facts.action != command.purpose:
        raise ConflictError("stock source action differs from its native execution purpose")
    current.actor.require_scope(
        "accounting.stock.reverse" if command.purpose == "REVERSE" else "accounting.stock.post",
        target=ScopePath(company_id=command.company_id),
    )
    if (
        any(
            getattr(facts, key) != getattr(command, key)
            for key in (
                "tenant_id",
                "company_id",
                "execution_id",
                "actor_user_id",
                "stock_date",
                "content_hash",
            )
        )
        or facts.issued_at > utcnow() + dt.timedelta(seconds=5)
        or facts.expires_at <= utcnow()
    ):
        raise ConflictError("stock source scope or lifetime differs from the accepted execution")
    if body.currency != current.context.base_currency or not finance.company_active:
        raise ConflictError("physical stock valuation requires the active company's base currency")
    features = {"inventory"}
    for item in facts.items:
        if item.lot_tracking:
            features.add("batch_tracking")
        if item.serial_tracking:
            features.add("serial_tracking")
        if item.expiry_required:
            features.add("expiry_tracking")
    if not features <= current.context.features:
        raise ConflictError("company tracking capabilities differ from this stock execution")
    if {line.item_id for line in body.lines} != {item.item_id for item in facts.items}:
        raise ConflictError("stock source item references differ")
    writable(current, STOCK_POSTING, {}, body.model_dump(exclude_none=True))
    for line in body.lines:
        writable(current, STOCK_MOVEMENT, {}, line.model_dump(exclude_none=True))
    return frozenset(features)


def permitted(item: StockItemFact, warehouse: StockWarehouseFact, operation: str) -> None:
    narrowed = next(
        (
            rule
            for rule in item.warehouse_permissions
            if rule.warehouse_id == warehouse.warehouse_id
        ),
        None,
    )
    if (
        not warehouse.is_active
        or operation not in warehouse.allowed_operations
        or narrowed is None
        or operation not in narrowed.allowed_operations
    ):
        raise ConflictError(
            "the product and warehouse policies do not allow this physical operation"
        )
    if (
        warehouse.kind != "INTERNAL_TRANSIT"
        and item.allowed_warehouse_ids is not None
        and warehouse.warehouse_id not in item.allowed_warehouse_ids
    ):
        raise ConflictError("this product is not allowed in the selected warehouse")


async def opening_coverage(
    db: AsyncSession, company: uuid.UUID, inventory_account_id: uuid.UUID
) -> None:
    reversed_journal = aliased(Journal)
    claimed = opening_claimed(company, JournalLine.id).scalar_subquery()
    uncovered = await db.scalar(
        select(JournalLine.id)
        .join(Journal, JournalLine.journal_id == Journal.id)
        .outerjoin(
            reversed_journal,
            (reversed_journal.reversal_of_id == Journal.id) & (reversed_journal.status == "POSTED"),
        )
        .where(
            JournalLine.company_id == company,
            Journal.company_id == company,
            Journal.kind == "OPENING",
            Journal.status == "POSTED",
            reversed_journal.id.is_(None),
            JournalLine.account_id == inventory_account_id,
            (JournalLine.side != "DEBIT") | (JournalLine.base_amount != claimed),
        )
        .limit(1)
    )
    if uncovered:
        raise ConflictError(
            "complete the stock quantities linked to the GL opening value before trading"
        )


async def bridge_opening(
    ledger: StockLedger,
    current: Access,
    leg: Leg,
    line_id: uuid.UUID,
    amount: Decimal,
    policy: StockAccountPolicy,
) -> None:
    line = await company_object(
        ledger.db, JournalLine, line_id, company_id=ledger.posting.company_id, lock=True
    )
    journal = await company_object(
        ledger.db, Journal, line.journal_id, company_id=ledger.posting.company_id
    )
    reversed_journal = await ledger.db.scalar(
        select(Journal.id)
        .where(
            Journal.company_id == journal.company_id,
            Journal.reversal_of_id == journal.id,
            Journal.status == "POSTED",
        )
        .limit(1)
    )
    if (
        journal.kind != "OPENING"
        or journal.status != "POSTED"
        or reversed_journal
        or line.side != "DEBIT"
        or line.account_id != policy.inventory_account_id
        or line.currency != ledger.posting.currency
    ):
        raise ConflictError(
            "linked stock opening requires its posted base-currency inventory opening debit"
        )
    used = await ledger.db.scalar(opening_claimed(ledger.posting.company_id, line.id))
    if used is None or used + amount > line.base_amount:
        raise ConflictError("stock opening value exceeds the unclaimed posted GL opening value")
    ledger.add(
        StockOpeningBridge,
        value_entry_id=leg.value_entry_id,
        journal_line_id=line.id,
        amount=amount,
    )


async def apply(
    db: AsyncSession,
    current: Access,
    command: ExecutionCommand,
    intent: VoucherMoneyIntent,
    facts: StockFenceFacts,
    *,
    preview: bool = False,
) -> StockEffects:
    body, _ = captured(command)
    if preview and not db.info.get(FLAG):
        raise ConflictError("stock preview must run in an always-rolled-back quote")
    features = source_scope(current, command, body, facts, preview=preview)
    await assert_retained(db, command.company_id, facts)
    if command.purpose == "REVERSE":
        from accounting.tasks.stock_reverse_effects import apply as reverse_apply

        return await reverse_apply(db, current, command, intent, facts, body, features)
    if command.purpose != "POST":
        raise ValidationFailedError("stock posting requires its common commit purpose")
    from accounting.tasks.stock_opening_control import claim as claim_opening
    from accounting.tasks.stock_opening_control import require_posting

    opening_control = await require_posting(db, command.company_id, body)
    assert command.posting_date is not None and command.stock_date is not None
    finance = financial_context(current)
    policy = await effective(db, current, command.posting_date)
    if body.action == "OPENING":
        if (
            command.stock_date != finance.books_begin_date
            or command.posting_date != finance.books_begin_date
        ):
            raise ConflictError("stock opening dates must equal the company's books-begin date")
        cancelled = aliased(StockPosting)
        trading = await db.scalar(
            select(StockPosting.id)
            .outerjoin(
                cancelled,
                (cancelled.company_id == StockPosting.company_id)
                & (cancelled.reverses_id == StockPosting.id),
            )
            .where(
                StockPosting.company_id == command.company_id,
                StockPosting.action.not_in(("OPENING", "REVERSAL")),
                cancelled.id.is_(None),
            )
            .limit(1)
        )
        if trading and (opening_control is None or opening_control.item_id is None):
            raise ConflictError("stock opening is closed after physical trading has started")
        if body.opening_mode == "COMBINED":
            # A reviewed combined opening cannot duplicate an existing imported
            # inventory debit. Its physical detail must link to that debit first.
            await opening_coverage(db, command.company_id, policy.inventory_account_id)
    else:
        await opening_coverage(db, command.company_id, policy.inventory_account_id)
    goods_cost: dict[uuid.UUID, Decimal] = {}
    invoice_money: MoneyInput | None = None
    if body.action == "PURCHASE_INVOICE":
        # B24: the accepted bill values its goods at landed cost, and its own distribution
        # (inventory, GST, supplier bill) is this execution's journal.
        from accounting.tasks.invoice_execution import resolve_goods

        _, bill, invoice_money, _ = await resolve_goods(db, current, command, facts)
        goods_cost = {row.key: row.stock_cost for row in bill.lines if row.stock_cost is not None}
    posting = StockPosting(
        **values(current),
        intent_id=intent.id,
        execution_id=command.execution_id,
        operation_id=command.operation_id,
        voucher_id=command.voucher_id,
        revision_id=command.revision_id,
        action=body.action,
        stock_date=command.stock_date,
        posting_date=command.posting_date,
        currency=body.currency,
        journal_id=intent.journal_id,
        reverses_id=None,
        account_policy_id=policy.id,
        content_hash=command.content_hash,
        source_facts={
            "stock": body.model_dump(mode="json"),
            "catalog": facts.model_dump(mode="json"),
        },
    )
    db.add(posting)
    await db.flush()
    ledger = StockLedger(
        db,
        posting,
        actor_id=command.actor_user_id,
        timezone=finance.timezone,
        places=finance.amount_precision,
        rounding=finance.rounding_mode,
    )
    ledger.observe(policy)
    if opening_control is not None:
        ledger.observe(opening_control)
    items = {item.item_id: item for item in facts.items}
    warehouses = {warehouse.warehouse_id: warehouse for warehouse in facts.warehouses}
    bins = {bin_row.bin_id: bin_row for bin_row in facts.bins}
    root_lines = command.source_payload.get("lines")
    if not isinstance(root_lines, list) or len(root_lines) != len(body.lines):
        raise ConflictError("stock lines must match the accepted common voucher item lines")
    common = {row.get("line_key"): row.get("item") for row in root_lines if isinstance(row, dict)}
    totals: dict[uuid.UUID, Decimal] = {}
    movements = []

    def entry(account: uuid.UUID, signed: Decimal) -> None:
        totals[account] = totals.get(account, ZERO) + signed

    ordered_lines = (
        sorted(
            body.lines,
            key=lambda line: (
                line.opening.received_on or body.stock_date,
                line.opening.cohort_order,
                line.opening.source_key,
            )
            if line.opening
            else (body.stock_date, 1, str(line.line_id)),
        )
        if body.action == "OPENING"
        else body.lines
    )
    for line in ordered_lines:
        item = items[line.item_id]
        from accounting.domain.stock_quantity import validate_capture

        validate_capture(line, item, body.action)
        if line.opening:
            opening_unit = next(
                (
                    unit
                    for unit in item.opening_units
                    if unit.revision_id == line.opening.unit_revision_id
                    and unit.unit_id == line.opening.entered_unit_id
                    and unit.item_id == item.item_id
                ),
                None,
            )
            if opening_unit is None:
                raise ConflictError("opening unit conversion is unavailable or changed")
            calculation = calculate_opening(
                entered_quantity=line.opening.entered_quantity,
                numerator=opening_unit.numerator,
                denominator=opening_unit.denominator,
                conversion_mode=opening_unit.conversion_mode,
                measured_base_quantity=line.opening.measured_base_quantity,
                entered_increment=opening_unit.quantity_increment,
                base_increment=item.quantity_increment,
                entered_places=opening_unit.quantity_decimal_places,
                base_places=item.quantity_decimal_places,
                serialized=item.serial_tracking,
                cost_mode=line.opening.cost_mode,
                unit_cost=line.opening.unit_cost,
                priced_quantity=line.opening.priced_quantity,
                received_value=line.received_value,
                places=finance.amount_precision,
                rounding=finance.rounding_mode,
            )
            if calculation.base_quantity != line.quantity:
                raise ValidationFailedError("opening entered and base quantities do not agree")
        warehouse = warehouses.get(line.warehouse_id)
        captured_item = common.get(str(line.line_id))
        if (
            not isinstance(captured_item, dict)
            or captured_item.get("item_id") != str(item.item_id)
            or type(captured_item.get("item_version")) is not int
            or captured_item.get("item_version") != item.item_version
            or captured_item.get("unit_id") != str(item.base_unit_id)
        ):
            raise ConflictError("physical lines differ from their accepted base-unit item capture")
        try:
            if (
                not isinstance(captured_item.get("actual_quantity"), str)
                or not isinstance(captured_item.get("billed_quantity"), str)
                or exact_decimal(captured_item["actual_quantity"]) != line.quantity
                or exact_decimal(captured_item["billed_quantity"])
                != (line.quantity if body.action == "PURCHASE_INVOICE" else 0)
            ):
                raise MoneyError(
                    "physical notes require actual base quantity and zero billed quantity"
                )
        except MoneyError as exc:
            raise ValidationFailedError(
                "physical quantities differ from the accepted stock capture"
            ) from exc
        if warehouse is None or warehouse.kind == "INTERNAL_TRANSIT":
            raise ConflictError("ordinary stock must select an actual company warehouse")
        if item.status != "ACTIVE" or item.family_status != "ACTIVE":
            if body.action not in {"CUSTOMER_RETURN", "SUPPLIER_RETURN"}:
                raise ConflictError("new stock operations require active products")
        if (body.action in {"RECEIPT", "PURCHASE_INVOICE"} and not item.purchasable) or (
            body.action == "DISPATCH" and not item.sellable
        ):
            raise ConflictError(
                "this product's transaction capabilities do not allow the operation"
            )
        permitted(item, warehouse, OPERATIONS[body.action])
        for bin_id, warehouse_id in (
            (line.bin_id, line.warehouse_id),
            (line.destination_bin_id, line.destination_warehouse_id),
        ):
            if bin_id and (
                bin_id not in bins
                or not bins[bin_id].is_active
                or bins[bin_id].warehouse_id != warehouse_id
            ):
                raise ConflictError("stock bin does not belong to the selected active warehouse")
        if body.action == "COUNT":
            from accounting.tasks.stock_count_effects import apply as apply_count

            leg = await apply_count(ledger, current, line, item, warehouse)
            if leg is not None:
                movements.append(leg)
                entry(policy.inventory_account_id, leg.value)
                entry(policy.variance_account_id, -leg.value)
        elif body.action == "PURCHASE_INVOICE":
            if line.line_id not in goods_cost:
                raise ConflictError("a goods line requires its accepted landed cost")
            leg = await ledger.receive(line, item, warehouse, value=goods_cost[line.line_id])
            movements.append(leg)
        elif body.action in {"OPENING", "RECEIPT"}:
            assert line.received_value is not None
            try:
                exact_decimal(line.received_value, decimal_places=finance.amount_precision)
            except MoneyError as exc:
                raise ValidationFailedError(
                    "review received value at company monetary precision"
                ) from exc
            leg = await ledger.receive(line, item, warehouse, value=line.received_value)
            movements.append(leg)
            if body.action == "OPENING":
                assert opening_control is not None
                await claim_opening(db, current, opening_control, posting, line, leg.movement_id)
            if body.action == "OPENING" and body.opening_mode == "LINKED_GL":
                if line.received_value:
                    assert line.opening_journal_line_id is not None
                    await bridge_opening(
                        ledger,
                        current,
                        leg,
                        line.opening_journal_line_id,
                        line.received_value,
                        policy,
                    )
            else:
                entry(policy.inventory_account_id, leg.value)
                entry(
                    policy.opening_offset_account_id
                    if body.action == "OPENING"
                    else policy.receipt_clearing_account_id,
                    -leg.value,
                )
        elif body.action == "DISPATCH":
            leg = await ledger.issue(line, item, warehouse)
            movements.append(leg)
            entry(policy.inventory_account_id, leg.value)
            entry(policy.dispatch_clearing_account_id, -leg.value)
        elif body.action in {"TRANSFER", "TRANSFER_DISPATCH"}:
            destination = (
                warehouses.get(line.destination_warehouse_id)
                if line.destination_warehouse_id
                else None
            )
            if destination is None or destination.kind == "INTERNAL_TRANSIT":
                raise ConflictError("transfer requires its actual company destination")
            permitted(item, destination, "TRANSFER_IN")
            if body.action == "TRANSFER":
                movements.extend(await ledger.transfer(line, item, warehouse, destination))
            else:
                transit = next(
                    (row for row in facts.warehouses if row.kind == "INTERNAL_TRANSIT"), None
                )
                if transit is None:
                    raise ConflictError("company reserved transit source is unavailable")
                permitted(item, transit, "TRANSFER_IN")
                movements.extend(
                    await transfer_dispatch(ledger, line, item, warehouse, transit, destination)
                )
        elif body.action == "TRANSFER_RECEIPT":
            transit = next(
                (row for row in facts.warehouses if row.kind == "INTERNAL_TRANSIT"), None
            )
            if transit is None:
                raise ConflictError("company reserved transit source is unavailable")
            permitted(item, transit, "TRANSFER_OUT")
            outward, inward, _ = await transfer_receive(ledger, line, item, warehouse, transit)
            movements.extend((outward, inward))
        else:
            leg, source = await (
                customer_return(ledger, line, item, warehouse)
                if body.action == "CUSTOMER_RETURN"
                else supplier_return(ledger, line, item, warehouse)
            )
            movements.append(leg)
            if source.posting.account_policy_id is None:
                raise ConflictError(
                    "original physical source has no retained clearing-account policy"
                )
            original_policy = await ledger.scoped(
                StockAccountPolicy, source.posting.account_policy_id
            )
            entry(policy.inventory_account_id, leg.value)
            if body.action == "CUSTOMER_RETURN":
                entry(original_policy.dispatch_clearing_account_id, -leg.value)
            else:
                entry(original_policy.receipt_clearing_account_id, source.value)
                entry(policy.variance_account_id, -leg.value - source.value)
    if sum(totals.values(), ZERO):
        raise ConflictError("native stock value and clearing account distribution do not balance")
    accounts = []
    for account_id, signed in sorted(totals.items()):
        if signed:
            account = await company_object(db, Account, account_id, company_id=command.company_id)
            ledger.observe(account)
            accounts.append(
                AccountEntry(
                    line_key=account_id,
                    account_id=account_id,
                    source_version=account.row_version,
                    side="DEBIT" if signed > 0 else "CREDIT",
                    currency=body.currency,
                    amount=abs(signed),
                )
            )
    await db.flush()
    money = MoneyInput(accounts=tuple(accounts)) if accounts else None
    if invoice_money is not None:
        debits = sum(
            (
                row.amount
                for row in invoice_money.accounts
                if row.line_key in goods_cost
                and row.account_id == policy.inventory_account_id
                and row.side == "DEBIT"
            ),
            ZERO,
        )
        if debits != sum((leg.value for leg in movements), ZERO) or accounts:
            raise ConflictError("the bill's inventory value differs from its stock movements")
        for row in invoice_money.accounts:
            ledger.observe(
                await company_object(db, Account, row.account_id, company_id=command.company_id)
            )
        money = invoice_money
    semantic = {
        "effects": semantic_effects(ledger),
        "money": money.model_dump(mode="json") if money else None,
        "company_configuration_hash": finance.configuration_hash,
        "account_policy_id": str(policy.id),
    }
    features = actual_tracking_features(ledger, current, features)
    return StockEffects(
        posting.id,
        tuple(movements),
        money,
        features,
        semantic,
        semantic_hash(semantic),
    )
