"""Prepared journal posting, serialized numbers and append-only reversal drafts."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.command_transaction import participating_session
from billing_platform.db import tenant_scope
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PlatformError
from billing_platform.idempotency import CommandResult
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from identity_posting import PostingClient, Receipt, ReservationError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.bank_reconciliation import BankReconciliationSession
from accounting.models.exchange_rates import ExchangeRateUsage
from accounting.models.fiscal import FiscalYear
from accounting.models.ledger import DocumentSequence, Journal, JournalLine
from accounting.models.masters import Account
from accounting.resources import BY_NAME
from accounting.schemas.ledger import JournalCreate, JournalReverse, JournalVoid
from accounting.schemas.masters import ExpectedVersion
from accounting.tasks.access import writable
from accounting.tasks.commands import audit, values_of
from accounting.tasks.exchange_rates import approved_for
from accounting.tasks.financial_commands import (
    FinancialEffect,
    financial_command,
    financial_context,
    mark_first_posted,
)
from accounting.tasks.fiscal import posting_period, setup
from accounting.tasks.journal_drafts import create_in_transaction, line_input, lines, validate_lines


class PostingDependencyError(PlatformError):
    status_code = 503
    code = "posting_authority_unavailable"


async def tax_exempt(
    db: AsyncSession, row: Journal, stored_lines: list[JournalLine]
) -> frozenset[uuid.UUID]:
    from accounting.tasks.voucher_tax import generated_accounts, stored

    return generated_accounts(await stored(db, row), stored_lines)


async def record_approved_rate_usage(
    db: AsyncSession, access: Access, journal: Journal, stored_lines: list[JournalLine]
) -> None:
    if journal.kind == "REVERSAL" or (
        journal.kind == "OPENING"
        and (
            journal.source_type == "financial_opening_chunk"
            or journal.source_system == "master-creation"
        )
    ):
        # Migration rates/carrying values come from reviewed historical evidence.
        # A coincidentally matching cutover-day quote was not their valuation source.
        return
    for line in stored_lines:
        if line.currency == journal.base_currency or line.amount == 0:
            continue
        quote = await approved_for(
            db,
            journal.company_id,
            line.currency,
            journal.base_currency,
            "ACCOUNTING",
            journal.posting_date,
        )
        if quote is None or quote.rate != line.exchange_rate:
            continue  # Legacy caller rate remains unavailable for governed-FX activation.
        usage = ExchangeRateUsage(
            id=uuid7(),
            tenant_id=access.actor.tenant_id,
            company_id=journal.company_id,
            journal_line_id=line.id,
            quote_id=quote.id,
            purpose="ACCOUNTING",
            effective_date=quote.effective_date,
            rate=quote.rate,
            source_sha256=quote.source_sha256,
            created_by=access.actor.user_id,
            updated_by=access.actor.user_id,
        )
        db.add(usage)
        event = "accounting.exchange_rate_usage.create"
        emit(
            db,
            aggregate_type="accounting.exchange_rate_usage",
            aggregate_id=usage.id,
            event_type=event,
            tenant_id=access.actor.tenant_id,
            payload=audit_payload(
                action=event,
                category="money",
                entity_type="accounting.exchange_rate_usage",
                entity_id=usage.id,
                actor_user_id=access.actor.user_id,
                company_id=journal.company_id,
            )
            | {"actor_type": "user"},
        )
    await db.flush()


def intent_values(row: Journal) -> dict[str, Any]:
    if row.prepared_by is None:
        raise ConflictError("journal posting intent is unavailable")
    return {
        "company_id": str(row.company_id),
        "operation_id": str(row.id),
        "actor_user_id": str(row.prepared_by),
        "configuration_hash": row.configuration_hash,
        "features": list(row.features),
        "posted_at": row.posted_at.isoformat() if row.posted_at else None,
    }


async def posting_delivery_values(
    db: AsyncSession, row: Journal, outcome: str
) -> tuple[str, dict[str, Any]]:
    from accounting.models.stock import StockExecutionPlan
    from accounting.models.voucher_money import VoucherMoneyIntent

    payload = intent_values(row)
    execution = await db.scalar(
        select(VoucherMoneyIntent.execution_id)
        .join(
            StockExecutionPlan,
            (StockExecutionPlan.tenant_id == VoucherMoneyIntent.tenant_id)
            & (StockExecutionPlan.company_id == VoucherMoneyIntent.company_id)
            & (StockExecutionPlan.intent_id == VoucherMoneyIntent.id),
        )
        .where(
            VoucherMoneyIntent.company_id == row.company_id, VoucherMoneyIntent.journal_id == row.id
        )
    )
    if execution is not None:
        payload["stock_execution_id"] = str(execution)
    return (
        "accounting.stock_posting." if execution is not None else "accounting.company_posting."
    ) + outcome, payload


async def prepare(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    key: str,
) -> CommandResult[BaseModel]:
    spec = FINANCIAL_BY_NAME["journal"]

    async def mutate(db: AsyncSession) -> FinancialEffect:
        return await prepare_in_transaction(db, access, object_id, body)

    return await financial_command(
        factory,
        access,
        spec,
        "prepare",
        body,
        key,
        mutate,
        permission="ledger.post_journal",
        object_id=object_id,
    )


async def allocate_number(
    db: AsyncSession, access: Access, row: Journal, fiscal_year_id: uuid.UUID
) -> str:
    year = await company_object(db, FiscalYear, fiscal_year_id, company_id=row.company_id)
    series = row.kind
    if row.kind == "VOUCHER":
        from accounting.tasks.voucher_money_effects import intent_for

        series = (await intent_for(db, row)).kind
    sequence = await db.scalar(
        select(DocumentSequence)
        .where(
            DocumentSequence.company_id == row.company_id,
            DocumentSequence.fiscal_year_id == fiscal_year_id,
            DocumentSequence.series_key == series,
        )
        .with_for_update()
    )
    if sequence is None:
        sequence = DocumentSequence(
            id=uuid7(),
            tenant_id=access.actor.tenant_id,
            company_id=row.company_id,
            fiscal_year_id=fiscal_year_id,
            series_key=series,
            next_value=1,
            created_by=access.actor.user_id,
            updated_by=access.actor.user_id,
        )
        db.add(sequence)
        await db.flush()
    if sequence.next_value >= 999999999:
        raise ConflictError("journal numbering series is exhausted")
    number = f"{series}/{year.code}/{sequence.next_value:06}"
    sequence.next_value += 1
    sequence.row_version += 1
    sequence.updated_by = access.actor.user_id
    return number


async def commit_post(db: AsyncSession, access: Access, row: Journal, receipt: Receipt) -> Journal:
    """Every caller holds the company lock; all ledger/subledger effects belong here."""
    if row.status != "PREPARED" or row.prepared_by != access.actor.user_id:
        raise ConflictError("journal has no matching prepared posting intent")
    if (
        receipt.operation_id != row.id
        or receipt.status != "pending"
        or receipt.configuration_hash != row.configuration_hash
        or not set(row.features) <= set(receipt.features)
    ):
        raise ConflictError("Identity reservation differs from journal posting intent")
    if row.configuration_hash != financial_context(access).configuration_hash:
        raise ConflictError("company configuration differs from the prepared journal")
    from accounting.tasks.subledger_posting import after_post, before_post

    await before_post(db, access, row)
    config = await setup(db, access)
    period = await posting_period(db, access, row.posting_date)
    stored_lines = await lines(db, row.company_id, row.id)
    from accounting.tasks.stock_gl import guard_journal

    await guard_journal(db, row, stored_lines)
    bank_ids = set(
        await db.scalars(
            select(Account.id).where(
                Account.company_id == row.company_id,
                Account.id.in_({line.account_id for line in stored_lines}),
                Account.kind == "BANK",
            )
        )
    )
    if bank_ids:
        closed_bank_period = await db.scalar(
            select(BankReconciliationSession.id)
            .where(
                BankReconciliationSession.company_id == row.company_id,
                BankReconciliationSession.account_id.in_(bank_ids),
                BankReconciliationSession.status == "FINALIZED",
                BankReconciliationSession.period_to >= row.posting_date,
            )
            .limit(1)
        )
        if closed_bank_period:
            raise ConflictError("amend finalized bank reconciliation before backdated bank posting")
    draft = JournalCreate(
        document_date=row.document_date,
        posting_date=row.posting_date,
        description=row.description,
        lines=[
            line_input(line, opening=row.kind in {"OPENING", "REVERSAL"}) for line in stored_lines
        ],
    )
    valued, accounts = await validate_lines(
        db, access, draft, kind=row.kind, exempt=await tax_exempt(db, row, stored_lines)
    )
    total = sum((item.base_amount for item in valued if item.entry.side == "DEBIT"), Decimal(0))
    if total != row.total_debit or any(
        line.base_amount != value.base_amount
        for line, value in zip(stored_lines, valued, strict=True)
    ):
        raise ConflictError("journal conversion differs from the prepared values")
    await record_approved_rate_usage(db, access, row, stored_lines)
    spec = FINANCIAL_BY_NAME["journal"]
    before = values_of(row, spec)
    incoming = {
        "status": "POSTED",
        "number": await allocate_number(db, access, row, period.fiscal_year_id),
        "fiscal_period_id": period.id,
        "reservation_id": receipt.reservation_id,
        "posted_at": utcnow(),
    }
    changed = writable(access, spec, before, before | incoming)
    for field, value in incoming.items():
        setattr(row, field, value)
    row.row_version += 1
    row.updated_by = access.actor.user_id
    account_spec = BY_NAME["account"]
    for account in accounts.values():
        if account.used_at is None:
            before_account = values_of(account, account_spec)
            fields = writable(
                access, account_spec, before_account, before_account | {"used_at": row.posted_at}
            )
            account.used_at = row.posted_at
            account.row_version += 1
            account.updated_by = access.actor.user_id
            await db.flush()
            audit(db, access, account_spec, account, "update", fields)
    assert row.posted_at is not None
    await mark_first_posted(db, access, config, row.posted_at)
    await db.flush()
    audit(db, access, spec, row, "post", changed)
    await after_post(db, access, row)
    from accounting.events.financial_contract import journal_posted

    await journal_posted(db, row)
    delivery_event, delivery_payload = await posting_delivery_values(db, row, "confirm")
    emit(
        db,
        aggregate_type="accounting.journal",
        aggregate_id=row.id,
        event_type=delivery_event,
        tenant_id=access.actor.tenant_id,
        payload=delivery_payload,
    )
    return row


async def post(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    key: str,
    client: PostingClient | None,
) -> CommandResult[BaseModel]:
    if (
        participating_session(
            factory, access.actor.tenant_id, access.context.company_id, access.actor.user_id
        )
        is not None
    ):
        raise ConflictError("posting requires an independent transaction boundary")
    if client is None:
        raise PostingDependencyError("Identity posting authorization is not configured")
    await prepare(factory, access, object_id, body, key)
    # No Accounting business transaction is alive during the remote reservation.
    with tenant_scope(access.actor.tenant_id):
        async with factory() as db:
            row = await company_object(db, Journal, object_id, company_id=access.context.company_id)
            already_posted = row.status == "POSTED"
            payload = intent_values(row)
    receipt: Receipt | None = None
    if not already_posted:
        try:
            receipt = await client.reserve(
                access.actor.tenant_id,
                access.context.company_id,
                operation_id=object_id,
                actor_user_id=uuid.UUID(payload["actor_user_id"]),
                configuration_hash=payload["configuration_hash"],
                features=payload["features"],
            )
        except ReservationError as exc:
            raise PostingDependencyError(
                "Identity posting authorization could not be obtained; retry the same request"
            ) from exc

    async def mutate(db: AsyncSession) -> FinancialEffect:
        current = await company_object(db, Journal, object_id, company_id=access.context.company_id)
        if current.status == "POSTED":
            return FinancialEffect(current)
        if receipt is None:
            raise ConflictError("journal posting state changed")
        return FinancialEffect(await commit_post(db, access, current, receipt))

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["journal"],
        "post",
        body,
        key,
        mutate,
        permission="ledger.post_journal",
        object_id=object_id,
    )


async def void(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: JournalVoid,
    key: str,
) -> CommandResult[BaseModel]:
    spec = FINANCIAL_BY_NAME["journal"]

    async def mutate(db: AsyncSession) -> FinancialEffect:
        row = await company_object(db, Journal, object_id, company_id=access.context.company_id)
        from accounting.models.voucher_money import VoucherMoneyIntent

        intent = await db.scalar(
            select(VoucherMoneyIntent.id).where(
                VoucherMoneyIntent.company_id == row.company_id,
                VoucherMoneyIntent.journal_id == row.id,
            )
        )
        if intent is not None or row.kind == "VOUCHER":
            raise ConflictError("voucher intents must cancel through their execution protocol")
        if row.status not in {"DRAFT", "PREPARED"} or row.row_version != body.expected_version:
            raise ConflictError("only a current unposted journal can be voided")
        prepared = row.status == "PREPARED"
        before = values_of(row, spec)
        changed = writable(
            access, spec, before, before | {"status": "VOID", "description": body.reason}
        )
        row.status = "VOID"
        row.description = body.reason
        row.row_version += 1
        row.updated_by = access.actor.user_id
        await db.flush()
        audit(db, access, spec, row, "void", changed)
        if prepared:
            delivery_event, delivery_payload = await posting_delivery_values(db, row, "abort")
            emit(
                db,
                aggregate_type="accounting.journal",
                aggregate_id=row.id,
                event_type=delivery_event,
                tenant_id=access.actor.tenant_id,
                payload=delivery_payload,
            )
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        spec,
        "void",
        body,
        key,
        mutate,
        permission="ledger.post_journal",
        object_id=object_id,
    )


async def reversal(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: JournalReverse,
    key: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        return await reversal_in_transaction(db, access, object_id, body)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["journal"],
        "reversal",
        body,
        key,
        mutate,
        permission="ledger.post_journal",
        object_id=object_id,
        status=201,
    )


async def prepare_in_transaction(
    db: AsyncSession, access: Access, object_id: uuid.UUID, body: ExpectedVersion
) -> FinancialEffect:
    """Caller owns the company fence; no remote reservation occurs here."""
    spec = FINANCIAL_BY_NAME["journal"]
    row = await company_object(db, Journal, object_id, company_id=access.context.company_id)
    from accounting.models.voucher_money import VoucherMoneyIntent

    intent = await db.scalar(
        select(VoucherMoneyIntent).where(
            VoucherMoneyIntent.company_id == row.company_id, VoucherMoneyIntent.journal_id == row.id
        )
    )
    if (row.kind == "VOUCHER" and intent is None) or (
        intent is not None and db.info.get("voucher_money_execution") != intent.execution_id
    ):
        raise ConflictError("voucher journals must post through their execution protocol")
    if row.status == "POSTED":
        return FinancialEffect(row)
    if row.status == "PREPARED":
        if row.prepared_by != access.actor.user_id or body.expected_version not in {
            row.row_version,
            row.prepared_version,
        }:
            raise ConflictError("journal is reserved by another posting attempt")
        return FinancialEffect(row)
    if row.status != "DRAFT" or row.row_version != body.expected_version:
        raise ConflictError("journal draft version changed")
    from accounting.tasks.subledger_posting import before_post

    await before_post(db, access, row)
    await posting_period(db, access, row.posting_date)
    stored_lines = await lines(db, row.company_id, row.id)
    from accounting.tasks.stock_gl import guard_journal

    await guard_journal(db, row, stored_lines)
    draft = JournalCreate(
        document_date=row.document_date,
        posting_date=row.posting_date,
        description=row.description,
        lines=[
            line_input(line, opening=row.kind in {"OPENING", "REVERSAL"}) for line in stored_lines
        ],
    )
    valued, _ = await validate_lines(
        db, access, draft, kind=row.kind, exempt=await tax_exempt(db, row, stored_lines)
    )
    if any(
        line.base_amount != value.base_amount
        for line, value in zip(stored_lines, valued, strict=True)
    ):
        raise ConflictError("journal conversion changed; recalculate the draft")
    facts = financial_context(access)
    features = (
        {"multi_currency"}
        if any(line.currency != row.base_currency for line in stored_lines)
        else set()
    )
    if any(line.party_id for line in stored_lines) and "credit_limits" in access.context.features:
        features.add("credit_limits")
    if intent is not None and intent.command.get("source_payload", {}).get("stock") is not None:
        from accounting.tasks.stock_execution import plan_for

        stock_plan = await plan_for(db, intent)
        features.update(stock_plan.effects["features"])
        if not features <= access.context.features:
            raise ConflictError("stock capabilities differ from the prepared company context")
    before = values_of(row, spec)
    incoming = {
        "status": "PREPARED",
        "prepared_by": access.actor.user_id,
        "prepared_at": utcnow(),
        "prepared_version": row.row_version,
        "configuration_hash": facts.configuration_hash,
        "features": sorted(features),
    }
    changed = writable(access, spec, before, before | incoming)
    for field, value in incoming.items():
        setattr(row, field, value)
    row.row_version += 1
    row.updated_by = access.actor.user_id
    await db.flush()
    audit(db, access, spec, row, "prepare", changed)
    return FinancialEffect(row)


async def reversal_in_transaction(
    db: AsyncSession, access: Access, object_id: uuid.UUID, body: JournalReverse
) -> FinancialEffect:
    """Append the reversal draft inside an already authorized company transaction."""
    original = await company_object(db, Journal, object_id, company_id=access.context.company_id)
    if original.status != "POSTED" or original.kind in {"REVERSAL", "REALIZED_FX"}:
        raise ConflictError("only an original posted journal can be reversed")
    if body.posting_date < original.posting_date:
        raise ConflictError("reversal cannot precede its original posting")
    await posting_period(db, access, body.posting_date)
    existing = await db.scalar(
        select(Journal).where(
            Journal.company_id == original.company_id,
            Journal.reversal_of_id == original.id,
            Journal.status != "VOID",
        )
    )
    if existing is not None:
        raise ConflictError("journal already has a reversal")
    from accounting.tasks.subledger_posting import validate_reversal

    await validate_reversal(db, access, original)
    original_lines = await lines(db, original.company_id, original.id)
    reversed_lines = [
        line_input(line, opening=original.kind == "OPENING").model_copy(
            update={"side": "CREDIT" if line.side == "DEBIT" else "DEBIT"}
        )
        for line in original_lines
    ]
    draft = JournalCreate(
        document_date=body.posting_date,
        posting_date=body.posting_date,
        description=body.reason,
        lines=reversed_lines,
    )
    row = await create_in_transaction(
        db,
        access,
        draft,
        kind="REVERSAL",
        source_system="accounting",
        source_type="reversal",
        source_id=str(uuid7()),
        reversal_of_id=original.id,
    )
    return FinancialEffect(row)
