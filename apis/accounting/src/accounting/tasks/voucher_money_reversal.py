"""Reverse original money facts and their owned allocations, never replay the original cash."""

import uuid

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution import ExecutionCommand

from accounting.api.auth import Access
from accounting.models.ledger import Journal
from accounting.models.subledger import Allocation
from accounting.models.voucher_money import (
    BankInstrument,
    BankInstrumentEvent,
    VoucherMoneyAllocation,
    VoucherMoneyIntent,
)
from accounting.schemas.ledger import JournalReverse
from accounting.schemas.subledger import AllocationReverse
from accounting.tasks.allocations import reverse_in_transaction
from accounting.tasks.finance_records import create_row
from accounting.tasks.fiscal import posting_period
from accounting.tasks.journal_posting import reversal_in_transaction


async def original(db: AsyncSession, command: ExecutionCommand) -> VoucherMoneyIntent:
    result = await db.scalar(
        select(VoucherMoneyIntent).where(
            VoucherMoneyIntent.company_id == command.company_id,
            VoucherMoneyIntent.execution_id == command.reversal_of_execution_id,
        )
    )
    if result is None or result.status != "COMMITTED" or result.voucher_id != command.voucher_id:
        raise ConflictError("original committed voucher execution is unavailable")
    accepted = ExecutionCommand.model_validate(result.command)
    if (
        accepted.purpose != "POST"
        or accepted.content_hash != command.content_hash
        or accepted.kind != command.kind
        or accepted.revision_id != command.revision_id
    ):
        raise ConflictError("reversal differs from its original voucher")
    if (
        command.posting_date is None
        or accepted.posting_date is None
        or command.posting_date < accepted.posting_date
        or not command.correction_reason
    ):
        raise ConflictError("a dated, explained reversal cannot precede its original")
    db.info["voucher_money_reversal"] = accepted.execution_id
    return result


async def bank_guard(db: AsyncSession, intent: VoucherMoneyIntent) -> list[BankInstrument]:
    instruments = list(
        await db.scalars(
            select(BankInstrument).where(
                BankInstrument.company_id == intent.company_id,
                BankInstrument.intent_id == intent.id,
            )
        )
    )
    for instrument in instruments:
        latest = await db.scalar(
            select(BankInstrumentEvent)
            .where(
                BankInstrumentEvent.company_id == intent.company_id,
                BankInstrumentEvent.instrument_id == instrument.id,
            )
            .order_by(BankInstrumentEvent.id.desc())
            .limit(1)
        )
        if latest and (latest.action in {"CLEARED", "RECONCILED", "UNRECONCILED", "REVERSED"}):
            raise ConflictError(
                "cleared bank movement requires a refund voucher; it cannot be cancelled"
            )
    return instruments


async def prepare(db: AsyncSession, current: Access, command: ExecutionCommand) -> Journal | None:
    intent = await original(db, command)
    assert command.posting_date is not None and command.correction_reason is not None
    await posting_period(db, current, command.posting_date)
    await bank_guard(db, intent)
    if intent.journal_id is None:
        return None
    effect = await reversal_in_transaction(
        db,
        current,
        intent.journal_id,
        JournalReverse(posting_date=command.posting_date, reason=command.correction_reason),
    )
    assert isinstance(effect.row, Journal)
    return effect.row


async def unwind(db: AsyncSession, current: Access, command: ExecutionCommand) -> list[uuid.UUID]:
    intent = await original(db, command)
    assert command.posting_date is not None and command.correction_reason is not None
    allocations = list(
        await db.scalars(
            select(VoucherMoneyAllocation.allocation_id).where(
                VoucherMoneyAllocation.company_id == intent.company_id,
                VoucherMoneyAllocation.intent_id == intent.id,
            )
        )
    )
    for identity in allocations:
        allocation = await company_object(db, Allocation, identity, company_id=intent.company_id)
        if allocation.reversal_date is None:
            await reverse_in_transaction(
                db,
                current,
                identity,
                AllocationReverse(
                    posting_date=command.posting_date,
                    reason=command.correction_reason,
                    expected_version=allocation.row_version,
                ),
            )
        elif allocation.reversal_date > command.posting_date:
            raise ConflictError("voucher reversal cannot precede its allocation reversal")
    for instrument in await bank_guard(db, intent):
        latest = await db.scalar(
            select(BankInstrumentEvent)
            .where(
                BankInstrumentEvent.company_id == intent.company_id,
                BankInstrumentEvent.instrument_id == instrument.id,
            )
            .order_by(BankInstrumentEvent.id.desc())
            .limit(1)
        )
        if latest is not None and latest.event_date > command.posting_date:
            raise ConflictError("voucher reversal cannot precede banking history")
        await create_row(
            db,
            current,
            "bank_instrument_event",
            instrument_id=instrument.id,
            action="REVERSED",
            event_date=command.posting_date,
            reference=None,
            reason=command.correction_reason,
        )
    return allocations
