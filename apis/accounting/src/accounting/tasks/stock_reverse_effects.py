"""Original stock, cost and GL lineage governs a compensating voucher reversal."""

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution import ExecutionCommand
from voucher_execution.money import AccountEntry, MoneyInput
from voucher_execution.stock import StockInput
from voucher_execution.stock_facts import StockFenceFacts

from accounting.api.auth import Access
from accounting.models.ledger import Journal
from accounting.models.masters import Account
from accounting.models.stock import StockPosition, StockPosting
from accounting.models.stock_tracking import StockLot
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.stock_resources import STOCK_POSTING
from accounting.tasks.access import writable
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.journal_drafts import lines as journal_lines
from accounting.tasks.stock_effects import StockEffects, actual_tracking_features, permitted
from accounting.tasks.stock_ledger import StockLedger
from accounting.tasks.stock_quote import semantic_effects, semantic_hash
from accounting.tasks.stock_reversal import guard, reverse_leg
from accounting.tasks.stock_transfers import transit_item
from accounting.tasks.voucher_money_effects import values
from accounting.tasks.voucher_money_reversal import original as original_intent

REVERSAL_OPERATION = "ADJUSTMENT"


async def apply(
    db: AsyncSession,
    current: Access,
    command: ExecutionCommand,
    intent: VoucherMoneyIntent,
    facts: StockFenceFacts,
    body: StockInput,
    features: frozenset[str],
) -> StockEffects:
    source_intent = await original_intent(db, command)
    original = await db.scalar(
        select(StockPosting)
        .where(
            StockPosting.company_id == command.company_id,
            StockPosting.intent_id == source_intent.id,
        )
        .with_for_update()
    )
    if original is None or body != StockInput.model_validate(original.source_facts.get("stock")):
        raise ConflictError("stock reversal differs from its original physical posting")
    historical = StockFenceFacts.model_validate(original.source_facts.get("catalog"))
    old_items = {item.item_id: item for item in historical.items}
    current_items = {item.item_id: item for item in facts.items}
    for identity, old in old_items.items():
        if identity not in current_items or any(
            getattr(old, key) != getattr(current_items[identity], key)
            for key in (
                "base_unit_id",
                "profile_id",
                "profile_revision_id",
                "lot_tracking",
                "serial_tracking",
                "valuation_method",
            )
        ):
            raise ConflictError(
                "reversal requires compatible original and current product stock definitions"
            )
    finance = financial_context(current)
    assert command.stock_date is not None and command.posting_date is not None
    posting = StockPosting(
        **values(current),
        intent_id=intent.id,
        execution_id=command.execution_id,
        operation_id=command.operation_id,
        voucher_id=command.voucher_id,
        revision_id=command.revision_id,
        action="REVERSAL",
        stock_date=command.stock_date,
        posting_date=command.posting_date,
        currency=original.currency,
        journal_id=intent.journal_id,
        reverses_id=original.id,
        account_policy_id=original.account_policy_id,
        content_hash=command.content_hash,
        source_facts={
            "stock": body.model_dump(mode="json"),
            "catalog": facts.model_dump(mode="json"),
        },
    )
    writable(
        current,
        STOCK_POSTING,
        {},
        {
            key: getattr(posting, key)
            for key in STOCK_POSTING.detail.model_fields
            if key not in {"id", "company_id", "row_version", "created_at", "updated_at"}
            and getattr(posting, key, None) is not None
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
    if original.action == "OPENING" and body.opening_control_id is not None:
        from accounting.models.stock_opening import StockOpeningControl

        opening_control = await company_object(
            db,
            StockOpeningControl,
            body.opening_control_id,
            company_id=command.company_id,
            lock=True,
        )
        if opening_control.status != "OPEN":
            raise ConflictError("reopen the reviewed cutover before correcting a stock opening")
        ledger.observe(opening_control)
        opening_control.row_version += 1
        opening_control.updated_by = current.actor.user_id
    warehouses = {warehouse.warehouse_id: warehouse for warehouse in facts.warehouses}
    movements = []
    for movement in await guard(ledger, original):
        position = await ledger.scoped(StockPosition, movement.position_id)
        if position.lot_id is not None:
            await ledger.scoped(StockLot, position.lot_id)
        warehouse = warehouses.get(position.warehouse_id)
        item = old_items.get(position.item_id)
        if warehouse is None or item is None:
            raise ConflictError("original stock position is outside current scoped source evidence")
        if warehouse.kind == "INTERNAL_TRANSIT":
            permitted(
                current_items[item.item_id],
                warehouse,
                "TRANSFER_IN" if movement.quantity < 0 else "TRANSFER_OUT",
            )
            item = transit_item(item)
        else:
            permitted(
                current_items[item.item_id],
                warehouse,
                "PURCHASE_RECEIPT" if original.action == "PURCHASE_INVOICE" else REVERSAL_OPERATION,
            )
        movements.append(await reverse_leg(ledger, movement, item, warehouse))
    entries = []
    if original.journal_id:
        journal = await company_object(
            db, Journal, original.journal_id, company_id=command.company_id
        )
        if journal.status != "POSTED" or journal.base_currency != original.currency:
            raise ConflictError("original posted stock GL evidence is unavailable")
        for line in await journal_lines(db, command.company_id, journal.id):
            account = await company_object(
                db, Account, line.account_id, company_id=command.company_id
            )
            ledger.observe(account)
            entries.append(
                AccountEntry(
                    line_key=line.id,
                    account_id=account.id,
                    source_version=account.row_version,
                    side="CREDIT" if line.side == "DEBIT" else "DEBIT",
                    currency=line.currency,
                    amount=line.amount,
                    exchange_rate=line.exchange_rate,
                )
            )
    money = MoneyInput(accounts=tuple(entries)) if entries else None
    await db.flush()
    semantic = {
        "effects": semantic_effects(ledger),
        "money": money.model_dump(mode="json") if money else None,
        "company_configuration_hash": finance.configuration_hash,
        "reverses_id": str(original.id),
    }
    features = actual_tracking_features(ledger, current, features)
    return StockEffects(
        posting.id, tuple(movements), money, features, semantic, semantic_hash(semantic)
    )
