"""Dated bank history under the company fence and financial field policy."""

import datetime as dt
import uuid

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError
from billing_platform.idempotency import CommandResult
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.banking import next_event
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.bank_reconciliation import BankReconciliationSession
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import AccountBankProfile
from accounting.models.voucher_money import BankInstrument, BankInstrumentEvent
from accounting.schemas.banking import BankAdoptRequest, BankEventCommand
from accounting.tasks.finance_records import create_row, require_fields
from accounting.tasks.financial_commands import FinancialEffect, financial_command


async def bank_session_open(
    db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, event_date: dt.date
) -> None:
    """Bank-date evidence may cross a closed GL year, but not a frozen BRS period."""
    closed = await db.scalar(
        select(BankReconciliationSession.id)
        .where(
            BankReconciliationSession.company_id == company_id,
            BankReconciliationSession.account_id == account_id,
            BankReconciliationSession.status == "FINALIZED",
            BankReconciliationSession.period_from <= event_date,
            BankReconciliationSession.period_to >= event_date,
        )
        .limit(1)
    )
    if closed:
        raise ConflictError("amend the finalized bank session before adding bank evidence")
    profile = await db.scalar(
        select(AccountBankProfile).where(
            AccountBankProfile.company_id == company_id,
            AccountBankProfile.account_id == account_id,
        )
    )
    if (
        profile
        and profile.reconciliation_start_date
        and event_date < profile.reconciliation_start_date
    ):
        later_closed = await db.scalar(
            select(BankReconciliationSession.id)
            .where(
                BankReconciliationSession.company_id == company_id,
                BankReconciliationSession.account_id == account_id,
                BankReconciliationSession.status == "FINALIZED",
            )
            .limit(1)
        )
        if later_closed:
            raise ConflictError("amend the finalized bank session before changing cutover evidence")


async def record(
    factory: async_sessionmaker[AsyncSession], current: Access, body: BankEventCommand, key: str
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        instrument = await company_object(
            db, BankInstrument, body.instrument_id, company_id=current.context.company_id
        )
        require_fields(
            current,
            "bank_instrument",
            {"mode", "instrument_date", "booking_date", "journal_line_id"},
            row=instrument,
        )
        require_fields(current, "bank_instrument_event", {"action", "event_date", "instrument_id"})
        if instrument.mode == "CASH":
            raise ConflictError("cash tender has no bank clearing lifecycle")
        last = await db.scalar(
            select(BankInstrumentEvent)
            .where(
                BankInstrumentEvent.company_id == instrument.company_id,
                BankInstrumentEvent.instrument_id == instrument.id,
            )
            .order_by(BankInstrumentEvent.id.desc())
            .limit(1)
        )
        if last is None or last.id != body.expected_event_id:
            raise ConflictError("bank instrument history changed; reload before retrying")
        await bank_session_open(db, instrument.company_id, instrument.account_id, body.event_date)
        next_event(
            last.action,
            body.action,
            last_date=last.event_date,
            date=body.event_date,
            instrument_date=instrument.instrument_date,
            reference=body.reference,
        )
        event = await create_row(
            db,
            current,
            "bank_instrument_event",
            instrument_id=instrument.id,
            action=body.action,
            event_date=body.event_date,
            reference=body.reference,
            reason=body.reason,
        )
        return FinancialEffect(event)

    return await financial_command(
        factory,
        current,
        FINANCIAL_BY_NAME["bank_instrument_event"],
        "create",
        body,
        key,
        mutate,
        permission="accounting.bank.manage",
        status=201,
    )


async def adopt(
    factory: async_sessionmaker[AsyncSession], current: Access, body: "BankAdoptRequest", key: str
) -> CommandResult[BaseModel]:
    """Attach reviewed evidence to one uncovered legacy/opening bank line; never change its GL."""
    from billing_platform.ids import uuid7

    from accounting.models.ledger import Journal, JournalLine
    from accounting.models.masters import Account

    async def mutate(db: AsyncSession) -> FinancialEffect:
        company = current.context.company_id
        line = await company_object(db, JournalLine, body.journal_line_id, company_id=company)
        journal = await company_object(db, Journal, line.journal_id, company_id=company)
        account = await company_object(db, Account, line.account_id, company_id=company)
        require_fields(
            current, "journal_line", {"journal_id", "account_id", "currency", "amount"}, row=line
        )
        require_fields(
            current, "journal", {"posting_date", "status", "row_version", "kind"}, row=journal
        )
        require_fields(current, "account", {"kind"}, row=account)
        require_fields(current, "bank_instrument", {"journal_line_id"})
        await bank_session_open(db, company, account.id, body.evidence_date)
        if (
            journal.status != "POSTED"
            or journal.row_version != body.expected_journal_version
            or journal.kind == "VOUCHER"
            or account.kind != "BANK"
            or body.evidence_date < journal.posting_date
            or line.amount <= 0
        ):
            raise ConflictError("only a current, posted legacy or opening bank line may be adopted")
        if body.mode == "CHEQUE" and body.instrument_date is None:
            raise ConflictError("cheque evidence requires its instrument date")
        covered = await db.scalar(
            select(BankInstrument.id)
            .where(BankInstrument.company_id == company, BankInstrument.journal_line_id == line.id)
            .limit(1)
        )
        reversed_journal = await db.scalar(
            select(Journal.id)
            .where(
                Journal.company_id == company,
                Journal.reversal_of_id == journal.id,
                Journal.status == "POSTED",
            )
            .limit(1)
        )
        if covered or reversed_journal or journal.kind == "REVERSAL":
            raise ConflictError("bank line already has evidence or has been reversed")
        instrument = await create_row(
            db,
            current,
            "bank_instrument",
            intent_id=None,
            journal_line_id=line.id,
            account_id=account.id,
            tender_key=uuid7(),
            mode=body.mode,
            reference=body.reference,
            instrument_date=body.instrument_date,
            booking_date=journal.posting_date,
            recognition="BOOK_DATE",
            currency=line.currency,
            amount=line.amount,
        )
        await create_row(
            db,
            current,
            "bank_instrument_event",
            instrument_id=instrument.id,
            action="BOOKED",
            event_date=journal.posting_date,
            reference=None,
            reason=body.reason,
        )
        return FinancialEffect(instrument)

    return await financial_command(
        factory,
        current,
        FINANCIAL_BY_NAME["bank_instrument"],
        "create",
        body,
        key,
        mutate,
        permission="accounting.bank.manage",
        status=201,
    )


async def legacy_reversal(
    db: AsyncSession, current: Access, original: Journal, reversal: Journal | None = None
) -> None:
    """Legacy bank evidence follows the existing journal reversal in the same transaction."""
    if original.kind == "VOUCHER":
        return  # The voucher executor owns those events and their cancellation receipt.
    instruments = list(
        await db.scalars(
            select(BankInstrument)
            .where(
                BankInstrument.company_id == original.company_id,
                BankInstrument.intent_id.is_(None),
                BankInstrument.journal_line_id.in_(
                    select(JournalLine.id).where(
                        JournalLine.company_id == original.company_id,
                        JournalLine.journal_id == original.id,
                    )
                ),
            )
            .limit(201)
        )
    )
    if len(instruments) > 200:
        raise ConflictError("journal bank evidence exceeds supported capacity")
    for instrument in instruments:
        last = await db.scalar(
            select(BankInstrumentEvent)
            .where(
                BankInstrumentEvent.company_id == original.company_id,
                BankInstrumentEvent.instrument_id == instrument.id,
            )
            .order_by(BankInstrumentEvent.id.desc())
            .limit(1)
        )
        if last is None or last.action in {"CLEARED", "RECONCILED", "UNRECONCILED", "REVERSED"}:
            raise ConflictError("cleared bank movement requires a refund voucher")
        if reversal is not None:
            if last.event_date > reversal.posting_date:
                raise ConflictError("reversal cannot precede bank history")
            await create_row(
                db,
                current,
                "bank_instrument_event",
                instrument_id=instrument.id,
                action="REVERSED",
                event_date=reversal.posting_date,
                reference=None,
                reason=reversal.description,
            )
