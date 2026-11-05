"""Inventory GL value is controlled by physical execution and reviewed openings."""

from billing_platform.errors import ConflictError
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.models.ledger import Journal, JournalLine
from accounting.models.stock import (
    StockAccountPolicy,
    StockExecutionPlan,
    StockOpeningBridge,
    StockValueEntry,
)
from accounting.models.voucher_money import VoucherMoneyIntent


async def guard_journal(db: AsyncSession, row: Journal, stored: list[JournalLine]) -> None:
    if row.kind == "REVERSAL" and row.reversal_of_id is not None:
        claimed = await db.scalar(
            select(
                func.sum(
                    case(
                        (StockValueEntry.amount > 0, StockOpeningBridge.amount),
                        else_=-StockOpeningBridge.amount,
                    )
                )
            )
            .select_from(StockOpeningBridge)
            .join(
                StockValueEntry,
                and_(
                    StockValueEntry.tenant_id == StockOpeningBridge.tenant_id,
                    StockValueEntry.company_id == StockOpeningBridge.company_id,
                    StockValueEntry.id == StockOpeningBridge.value_entry_id,
                ),
            )
            .join(
                JournalLine,
                and_(
                    JournalLine.tenant_id == StockOpeningBridge.tenant_id,
                    JournalLine.company_id == StockOpeningBridge.company_id,
                    JournalLine.id == StockOpeningBridge.journal_line_id,
                ),
            )
            .where(
                StockOpeningBridge.company_id == row.company_id,
                JournalLine.journal_id == row.reversal_of_id,
            )
        )
        if claimed:
            raise ConflictError("reverse linked stock opening before reversing its GL opening")
    account_ids = {line.account_id for line in stored}
    governed = await db.scalar(
        select(StockAccountPolicy.id)
        .where(
            StockAccountPolicy.company_id == row.company_id,
            StockAccountPolicy.inventory_account_id.in_(account_ids),
            StockAccountPolicy.valid_from <= row.posting_date,
        )
        .limit(1)
    )
    if governed is None:
        return
    if row.kind == "OPENING":
        from accounting.models.stock_opening import StockOpeningControl
        from accounting.tasks.stock_opening_control import active_claims

        control = await db.scalar(
            select(StockOpeningControl)
            .where(
                StockOpeningControl.company_id == row.company_id,
                StockOpeningControl.item_id.is_(None),
            )
            .with_for_update()
        )
        if control is not None and (
            control.status == "FINALIZED" or await active_claims(db, control)
        ):
            raise ConflictError(
                "reopen and reverse applied stock openings before changing inventory GL opening"
            )
        return
    if row.kind == "REVERSAL" and row.reversal_of_id is not None:
        original = await db.scalar(
            select(Journal).where(
                Journal.company_id == row.company_id, Journal.id == row.reversal_of_id
            )
        )
        if original is not None and original.kind == "OPENING":
            return  # Its physical bridge was checked above, including released claims.
    native = await db.scalar(
        select(StockExecutionPlan.id)
        .join(
            VoucherMoneyIntent,
            and_(
                VoucherMoneyIntent.tenant_id == StockExecutionPlan.tenant_id,
                VoucherMoneyIntent.company_id == StockExecutionPlan.company_id,
                VoucherMoneyIntent.id == StockExecutionPlan.intent_id,
            ),
        )
        .where(
            StockExecutionPlan.company_id == row.company_id,
            VoucherMoneyIntent.journal_id == row.id,
            VoucherMoneyIntent.status == "PREPARED",
        )
        .limit(1)
    )
    if row.kind not in {"VOUCHER", "REVERSAL"} or native is None:
        raise ConflictError(
            "inventory accounts require native stock execution or a controlled GL opening"
        )
