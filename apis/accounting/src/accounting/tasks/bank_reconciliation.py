"""Account-scoped statement evidence and reviewed, non-posting bank reconciliation."""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
import uuid
from decimal import Decimal
from itertools import pairwise
from typing import Any, Literal, TypeVar, cast

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.exact import exact_decimal
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.domain.statement_csv import CsvMapping, parse_statement
from accounting.domain.statement_matching import MatchPart, MatchPreview, MatchSource, preview
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.bank_reconciliation import (
    BankAdjustmentProposal,
    BankMatchEvent,
    BankOpeningItem,
    BankReconciliationPolicy,
    BankReconciliationSession,
    BankStatementEntry,
    BankStatementImport,
    BankStatementMapping,
)
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import Account, AccountBankProfile, Record
from accounting.models.voucher_money import BankInstrument, BankInstrumentEvent, VoucherMoneyIntent
from accounting.schemas.bank_reconciliation import (
    CandidateView,
    DuplicateDecision,
    MappingCreate,
    MatchCommand,
    OpeningCreate,
    PolicyCreate,
    ProposalCreate,
    ProposalDecision,
    SessionCreate,
    StatementUpload,
)
from accounting.tasks.access import readable, writable
from accounting.tasks.commands import setup_lock
from accounting.tasks.finance_records import require_fields
from accounting.tasks.financial_commands import financial_context


def authorize(access: Access, *, write: bool = False, scope: str | None = None) -> None:
    access.context.assert_current(access.actor, access.context.company_id)
    if write:
        financial_context(access)
    access.actor.require_scope(
        "accounting.bank.manage" if write else "accounting.bank.read",
        target=ScopePath(company_id=access.context.company_id),
    )
    access.actor.require_scope(
        scope or "accounting.statement.read",
        target=ScopePath(company_id=access.context.company_id),
    )


def audit(
    db: AsyncSession, access: Access, row: Any, action: str, reason: str | None = None
) -> None:
    entity = f"accounting.{row.__tablename__}"
    from billing_platform.audit_evidence import scalar

    from accounting.events.audit_contract import audit_event
    from accounting.events.evidence import BANK_SAFE_FIELDS

    event = audit_event(row.__tablename__, action)
    emit(
        db,
        aggregate_type=entity,
        aggregate_id=row.id,
        event_type=event,
        tenant_id=access.actor.tenant_id,
        payload=audit_payload(
            action=event,
            category="money",
            entity_type=entity,
            entity_id=row.id,
            actor_user_id=access.actor.user_id,
            company_id=access.context.company_id,
            reason=reason,
            changes={
                key: {"to": scalar(getattr(row, key))}
                for key in BANK_SAFE_FIELDS
                if hasattr(row, key)
            },
        )
        | {"actor_type": "user"},
    )


T = TypeVar("T", bound=Record)


def new(access: Access, model: type[T], **fields: Any) -> T:
    writable(access, FINANCIAL_BY_NAME[model.__tablename__], {}, fields)
    return model(
        id=uuid7(),
        tenant_id=access.actor.tenant_id,
        company_id=access.context.company_id,
        created_by=access.actor.user_id,
        updated_by=access.actor.user_id,
        **fields,
    )


def public(row: Record, access: Access) -> dict[str, Any]:
    spec = FINANCIAL_BY_NAME[row.__tablename__]
    values = {key: getattr(row, key) for key in spec.detail.model_fields if hasattr(row, key)}
    allowed = readable(access, spec, values)
    return {key: value for key, value in values.items() if key in allowed}


def guard_change(row: Record, access: Access, **fields: Any) -> None:
    spec = FINANCIAL_BY_NAME[row.__tablename__]
    before = {key: getattr(row, key) for key in spec.detail.model_fields if hasattr(row, key)}
    writable(access, spec, before, before | fields)


async def bank_account(
    db: AsyncSession, access: Access, account_id: uuid.UUID, currency: str | None = None
) -> Account:
    account = await company_object(db, Account, account_id, company_id=access.context.company_id)
    profile = await db.scalar(
        select(AccountBankProfile).where(
            AccountBankProfile.company_id == access.context.company_id,
            AccountBankProfile.account_id == account_id,
        )
    )
    if (
        account.kind != "BANK"
        or account.status != "ACTIVE"
        or profile is None
        or profile.reconciliation_start_date is None
    ):
        raise ConflictError("account is not an active company bank account")
    expected = account.currency or access.context.base_currency
    if account.currency_mode == "MULTI":
        raise ConflictError("bank reconciliation requires a fixed account currency")
    if currency is not None and currency != expected:
        raise ConflictError("statement currency differs from bank account currency")
    return account


async def opening_item(db: AsyncSession, access: Access, body: OpeningCreate) -> BankOpeningItem:
    authorize(access, write=True, scope="accounting.statement.review")
    await setup_lock(db, access)
    instrument = await company_object(
        db, BankInstrument, body.instrument_id, company_id=access.context.company_id
    )
    await bank_account(db, access, instrument.account_id, instrument.currency)
    profile = await db.scalar(
        select(AccountBankProfile).where(
            AccountBankProfile.company_id == access.context.company_id,
            AccountBankProfile.account_id == instrument.account_id,
        )
    )
    if (
        profile is None
        or profile.reconciliation_start_date != body.cutoff_date
        or instrument.booking_date >= body.cutoff_date
        or instrument.amount != body.amount
    ):
        raise ConflictError(
            "opening item must identify a pre-cutover bank instrument at its book amount"
        )
    latest_at_cutover = await db.scalar(
        select(BankInstrumentEvent)
        .where(
            BankInstrumentEvent.company_id == access.context.company_id,
            BankInstrumentEvent.instrument_id == instrument.id,
            BankInstrumentEvent.event_date < body.cutoff_date,
        )
        .order_by(BankInstrumentEvent.event_date.desc(), BankInstrumentEvent.id.desc())
        .limit(1)
    )
    if latest_at_cutover and latest_at_cutover.action in {"CLEARED", "RECONCILED", "REVERSED"}:
        raise ConflictError("instrument was already cleared or reversed before bank cutover")
    existing = await db.scalar(
        select(BankOpeningItem).where(
            BankOpeningItem.company_id == access.context.company_id,
            BankOpeningItem.account_id == instrument.account_id,
            BankOpeningItem.instrument_id == instrument.id,
        )
    )
    if existing:
        if existing.cutoff_date != body.cutoff_date or existing.amount != body.amount:
            raise ConflictError("opening bank item was already reviewed with different evidence")
        return existing
    closed = await db.scalar(
        select(BankReconciliationSession.id)
        .where(
            BankReconciliationSession.company_id == access.context.company_id,
            BankReconciliationSession.account_id == instrument.account_id,
            BankReconciliationSession.status == "FINALIZED",
        )
        .limit(1)
    )
    if closed:
        raise ConflictError("amend finalized bank sessions before changing opening items")
    row = new(
        access,
        BankOpeningItem,
        account_id=instrument.account_id,
        instrument_id=instrument.id,
        cutoff_date=body.cutoff_date,
        amount=exact_decimal(body.amount),
        currency=instrument.currency,
        reason=body.reason,
    )
    db.add(row)
    await db.flush()
    audit(db, access, row, "review", body.reason)
    return row


async def active_policy(
    db: AsyncSession, access: Access, account_id: uuid.UUID
) -> BankReconciliationPolicy | None:
    return cast(
        BankReconciliationPolicy | None,
        await db.scalar(
            select(BankReconciliationPolicy)
            .where(
                BankReconciliationPolicy.company_id == access.context.company_id,
                BankReconciliationPolicy.account_id == account_id,
            )
            .order_by(BankReconciliationPolicy.revision.desc())
            .limit(1)
        ),
    )


async def create_policy(
    db: AsyncSession, access: Access, body: PolicyCreate
) -> BankReconciliationPolicy:
    authorize(access, write=True, scope="accounting.statement.review")
    await setup_lock(db, access)
    await bank_account(db, access, body.account_id)
    latest = await active_policy(db, access, body.account_id)
    if latest and (
        latest.mode == body.mode
        and latest.match_window_days == body.match_window_days
        and latest.require_separate_reviewer == body.require_separate_reviewer
    ):
        return latest
    row = new(
        access,
        BankReconciliationPolicy,
        account_id=body.account_id,
        revision=(latest.revision + 1 if latest else 1),
        mode=body.mode,
        match_window_days=body.match_window_days,
        require_separate_reviewer=body.require_separate_reviewer,
    )
    db.add(row)
    await db.flush()
    audit(db, access, row, "publish")
    return row


async def create_mapping(
    db: AsyncSession, access: Access, body: MappingCreate
) -> BankStatementMapping:
    authorize(access, write=True, scope="accounting.statement.import")
    await setup_lock(db, access)
    await bank_account(db, access, body.account_id, body.currency)
    count = await db.scalar(
        select(func.max(BankStatementMapping.revision)).where(
            BankStatementMapping.company_id == access.context.company_id,
            BankStatementMapping.account_id == body.account_id,
        )
    )
    columns = body.model_dump(mode="json", exclude={"account_id", "currency"})
    latest = await db.scalar(
        select(BankStatementMapping)
        .where(
            BankStatementMapping.company_id == access.context.company_id,
            BankStatementMapping.account_id == body.account_id,
        )
        .order_by(BankStatementMapping.revision.desc())
        .limit(1)
    )
    if latest and latest.currency == body.currency and latest.columns == columns:
        return latest
    # Run the exact parser's mapping validation before publishing the revision.
    if len({value for key, value in columns.items() if key.endswith("_column") and value}) != len(
        [value for key, value in columns.items() if key.endswith("_column") and value]
    ):
        raise ValidationFailedError("bank statement mapping columns must be distinct")
    row = new(
        access,
        BankStatementMapping,
        account_id=body.account_id,
        revision=(count or 0) + 1,
        currency=body.currency,
        columns=columns,
    )
    db.add(row)
    await db.flush()
    audit(db, access, row, "publish")
    return row


def _csv_mapping(row: BankStatementMapping) -> CsvMapping:
    return CsvMapping(account_id=row.account_id, currency=row.currency, **row.columns)


async def upload(db: AsyncSession, access: Access, body: StatementUpload) -> BankStatementImport:
    authorize(access, write=True, scope="accounting.statement.import")
    await setup_lock(db, access)
    mapping = await company_object(
        db, BankStatementMapping, body.mapping_id, company_id=access.context.company_id
    )
    await bank_account(db, access, mapping.account_id, mapping.currency)
    if body.period_from > body.period_to:
        raise ValidationFailedError("invalid statement period")
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationFailedError("statement content is not valid base64") from exc
    parsed = parse_statement(raw, _csv_mapping(mapping))
    existing_import = await db.scalar(
        select(BankStatementImport).where(
            BankStatementImport.company_id == access.context.company_id,
            BankStatementImport.account_id == mapping.account_id,
            BankStatementImport.file_sha256 == parsed.file_sha256,
        )
    )
    if existing_import:
        if (
            existing_import.mapping_id != mapping.id
            or existing_import.period_from != body.period_from
            or existing_import.period_to != body.period_to
            or existing_import.opening_balance != body.opening_balance
            or existing_import.closing_balance != body.closing_balance
        ):
            raise ConflictError("same bank file was submitted with different controls")
        return existing_import
    if any(not body.period_from <= row.transaction_date <= body.period_to for row in parsed.rows):
        raise ValidationFailedError("bank row date is outside the statement period")
    opening = exact_decimal(body.opening_balance)
    closing = exact_decimal(body.closing_balance)
    movement = sum(
        (row.amount if row.side == "CREDIT" else -row.amount for row in parsed.rows), Decimal(0)
    )
    if opening + movement != closing:
        raise ValidationFailedError("statement opening, movements and closing do not agree")
    running = opening
    for source in parsed.rows:
        running += source.amount if source.side == "CREDIT" else -source.amount
        if source.running_balance is not None and source.running_balance != running:
            raise ValidationFailedError(
                "statement running balance differs from mapped row movements"
            )
    external_ids = {row.transaction_id for row in parsed.rows if row.transaction_id}
    previous = list(
        await db.scalars(
            select(BankStatementEntry)
            .join(BankStatementImport, BankStatementEntry.import_id == BankStatementImport.id)
            .where(
                BankStatementEntry.company_id == access.context.company_id,
                BankStatementEntry.account_id == mapping.account_id,
                BankStatementImport.status == "COMMITTED",
                or_(
                    BankStatementEntry.transaction_date.between(body.period_from, body.period_to),
                    BankStatementEntry.transaction_id.in_(external_ids),
                ),
            )
            .limit(10001)
        )
    )
    if len(previous) > 10000:
        raise ConflictError("statement overlap exceeds supported review window")
    by_id = {row.transaction_id: row for row in previous if row.transaction_id}
    by_hash = {row.row_sha256 for row in previous}
    batch = new(
        access,
        BankStatementImport,
        account_id=mapping.account_id,
        mapping_id=mapping.id,
        file_sha256=parsed.file_sha256,
        currency=mapping.currency,
        period_from=body.period_from,
        period_to=body.period_to,
        opening_balance=opening,
        closing_balance=closing,
        row_count=len(parsed.rows),
        status="PREVIEW",
        review_reason=None,
    )
    db.add(batch)
    await db.flush()
    for source in parsed.rows:
        prior = by_id.get(source.transaction_id) if source.transaction_id else None
        disposition = (
            "EXISTING"
            if prior and prior.row_sha256 == source.row_sha256
            else "AMBIGUOUS"
            if prior or source.row_sha256 in by_hash
            else "NEW"
        )
        db.add(
            new(
                access,
                BankStatementEntry,
                import_id=batch.id,
                account_id=mapping.account_id,
                line_number=source.line_number,
                transaction_date=source.transaction_date,
                side=source.side,
                amount=source.amount,
                currency=mapping.currency,
                reference=source.reference,
                description=source.description,
                transaction_id=source.transaction_id,
                row_sha256=source.row_sha256,
                review_status=disposition,
                running_balance=source.running_balance,
            )
        )
    await db.flush()
    audit(db, access, batch, "preview")
    return batch


async def decide_duplicate(
    db: AsyncSession, access: Access, entry_id: uuid.UUID, body: DuplicateDecision
) -> BankStatementEntry:
    authorize(access, write=True, scope="accounting.statement.review")
    await setup_lock(db, access)
    row = await company_object(
        db, BankStatementEntry, entry_id, company_id=access.context.company_id
    )
    batch = await company_object(
        db, BankStatementImport, row.import_id, company_id=access.context.company_id
    )
    if row.review_status == body.disposition:
        return row
    if batch.status != "PREVIEW" or row.review_status != "AMBIGUOUS":
        raise ConflictError("only an ambiguous preview row can be decided")
    guard_change(row, access, review_status=body.disposition)
    row.review_status = body.disposition
    row.row_version += 1
    row.updated_by = access.actor.user_id
    audit(db, access, row, "duplicate_decision", body.reason)
    return row


async def commit_import(
    db: AsyncSession, access: Access, import_id: uuid.UUID, reason: str
) -> BankStatementImport:
    authorize(access, write=True, scope="accounting.statement.review")
    await setup_lock(db, access)
    batch = await company_object(
        db, BankStatementImport, import_id, company_id=access.context.company_id
    )
    if batch.status == "COMMITTED":
        return batch
    policy = await active_policy(db, access, batch.account_id)
    if policy and policy.require_separate_reviewer and batch.created_by == access.actor.user_id:
        raise ConflictError("statement import requires a different reviewer")
    if batch.status != "PREVIEW":
        raise ConflictError("statement import is not reviewable")
    ambiguous = await db.scalar(
        select(BankStatementEntry.id)
        .where(
            BankStatementEntry.company_id == batch.company_id,
            BankStatementEntry.import_id == batch.id,
            BankStatementEntry.review_status == "AMBIGUOUS",
        )
        .limit(1)
    )
    if ambiguous:
        raise ConflictError("ambiguous statement duplicates need a decision")
    overlap = await db.scalar(
        select(BankStatementImport.id)
        .where(
            BankStatementImport.company_id == batch.company_id,
            BankStatementImport.account_id == batch.account_id,
            BankStatementImport.id != batch.id,
            BankStatementImport.status == "COMMITTED",
            BankStatementImport.period_from <= batch.period_to,
            BankStatementImport.period_to >= batch.period_from,
        )
        .limit(1)
    )
    if overlap:
        raise ConflictError(
            "statement period overlaps a committed import; use a non-overlapping bank export"
        )
    closed = await db.scalar(
        select(BankReconciliationSession.id)
        .where(
            BankReconciliationSession.company_id == batch.company_id,
            BankReconciliationSession.account_id == batch.account_id,
            BankReconciliationSession.status == "FINALIZED",
            BankReconciliationSession.period_from <= batch.period_to,
            BankReconciliationSession.period_to >= batch.period_from,
        )
        .limit(1)
    )
    if closed:
        raise ConflictError("amend the finalized bank session before committing a late statement")
    guard_change(batch, access, status="COMMITTED", review_reason=reason)
    batch.status = "COMMITTED"
    batch.review_reason = reason
    batch.row_version += 1
    batch.updated_by = access.actor.user_id
    audit(db, access, batch, "commit", reason)
    return batch


async def reject_import(
    db: AsyncSession, access: Access, import_id: uuid.UUID, reason: str
) -> BankStatementImport:
    authorize(access, write=True, scope="accounting.statement.review")
    await setup_lock(db, access)
    batch = await company_object(
        db, BankStatementImport, import_id, company_id=access.context.company_id
    )
    if batch.status == "REJECTED":
        if batch.review_reason != reason:
            raise ConflictError("statement preview was already rejected for another reason")
        return batch
    if batch.status != "PREVIEW":
        raise ConflictError("committed statement evidence cannot be rejected")
    guard_change(batch, access, status="REJECTED", review_reason=reason)
    batch.status = "REJECTED"
    batch.review_reason = reason
    batch.row_version += 1
    batch.updated_by = access.actor.user_id
    audit(db, access, batch, "reject", reason)
    return batch


async def _active_events(
    db: AsyncSession, access: Access, entry_ids: set[uuid.UUID], instrument_ids: set[uuid.UUID]
) -> list[BankMatchEvent]:
    if not entry_ids and not instrument_ids:
        return []
    from sqlalchemy import or_

    events = list(
        await db.scalars(
            select(BankMatchEvent)
            .where(
                BankMatchEvent.company_id == access.context.company_id,
                or_(
                    BankMatchEvent.statement_entry_id.in_(entry_ids),
                    BankMatchEvent.instrument_id.in_(instrument_ids),
                ),
            )
            .order_by(BankMatchEvent.id)
        )
    )
    reversed_ids = {event.reverses_id for event in events if event.reverses_id}
    return [event for event in events if event.reverses_id is None and event.id not in reversed_ids]


def _reference(value: str | None) -> str:
    return "".join(character for character in (value or "").casefold() if character.isalnum())


async def candidates(db: AsyncSession, access: Access, entry_id: uuid.UUID) -> list[CandidateView]:
    authorize(access)
    entry = await company_object(
        db, BankStatementEntry, entry_id, company_id=access.context.company_id
    )
    batch = await company_object(
        db, BankStatementImport, entry.import_id, company_id=access.context.company_id
    )
    require_fields(
        access,
        "bank_statement_entry",
        {"account_id", "currency", "side", "amount", "transaction_date", "reference"},
        row=entry,
    )
    require_fields(
        access,
        "bank_instrument",
        {"account_id", "currency", "amount", "booking_date", "reference", "journal_line_id"},
    )
    if batch.status != "COMMITTED" or entry.review_status not in {"NEW", "ACCEPTED"}:
        raise ConflictError("candidate search requires accepted committed statement evidence")
    policy = await active_policy(db, access, entry.account_id)
    if policy is None or policy.mode == "MANUAL_ONLY":
        return []
    minimum = entry.transaction_date - dt.timedelta(days=policy.match_window_days)
    maximum = entry.transaction_date + dt.timedelta(days=policy.match_window_days)
    instruments = list(
        await db.scalars(
            select(BankInstrument)
            .where(
                BankInstrument.company_id == access.context.company_id,
                BankInstrument.account_id == entry.account_id,
                BankInstrument.currency == entry.currency,
                BankInstrument.booking_date >= minimum,
                BankInstrument.booking_date <= maximum,
            )
            .order_by(BankInstrument.booking_date, BankInstrument.id)
            .limit(201)
        )
    )
    if len(instruments) > 200:
        raise ConflictError("candidate window exceeds the supported review limit")
    active = await _active_events(db, access, {entry.id}, {row.id for row in instruments})
    used_entry = sum(
        (event.amount for event in active if event.statement_entry_id == entry.id), Decimal(0)
    )
    used_book: dict[uuid.UUID, Decimal] = {}
    for event in active:
        used_book[event.instrument_id] = (
            used_book.get(event.instrument_id, Decimal(0)) + event.amount
        )
    remaining_entry = entry.amount - used_entry
    if remaining_entry <= 0:
        return []
    line_sides: dict[uuid.UUID, str] = dict(
        (
            await db.execute(
                select(JournalLine.id, JournalLine.side).where(
                    JournalLine.company_id == access.context.company_id,
                    JournalLine.id.in_({row.journal_line_id for row in instruments}),
                )
            )
        )
        .tuples()
        .all()
    )
    suggestions: list[CandidateView] = []
    for instrument in instruments:
        side = line_sides.get(instrument.journal_line_id)
        remaining_book = instrument.amount - used_book.get(instrument.id, Decimal(0))
        if side is None or remaining_book <= 0 or ((entry.side == "CREDIT") != (side == "DEBIT")):
            continue
        same_ref = bool(_reference(entry.reference)) and _reference(entry.reference) == _reference(
            instrument.reference
        )
        same_amount = remaining_entry == remaining_book
        reason: Literal["REFERENCE_AND_AMOUNT", "AMOUNT_AND_DATE", "POTENTIAL"] = (
            "REFERENCE_AND_AMOUNT"
            if same_ref and same_amount
            else "AMOUNT_AND_DATE"
            if same_amount
            else "POTENTIAL"
        )
        rank = 0 if reason == "REFERENCE_AND_AMOUNT" else 1 if reason == "AMOUNT_AND_DATE" else 2
        suggestions.append(
            CandidateView(
                statement_entry_id=entry.id,
                instrument_id=instrument.id,
                remaining_statement=remaining_entry,
                remaining_book=remaining_book,
                rank=rank,
                reason=reason,
            )
        )
    return sorted(suggestions, key=lambda row: (row.rank, str(row.instrument_id)))[:50]


async def match(
    db: AsyncSession, access: Access, body: MatchCommand, *, dry_run: bool = False
) -> list[BankMatchEvent] | MatchPreview:
    authorize(access, write=True, scope="accounting.bank_match.manage")
    require_fields(
        access,
        "bank_statement_entry",
        {"account_id", "currency", "side", "amount", "transaction_date", "review_status"},
    )
    require_fields(
        access,
        "bank_instrument",
        {"account_id", "currency", "amount", "journal_line_id", "booking_date"},
    )
    await setup_lock(db, access)  # company-wide serialization, including competing matches
    existing = list(
        await db.scalars(
            select(BankMatchEvent).where(
                BankMatchEvent.company_id == access.context.company_id,
                BankMatchEvent.group_id == body.group_id,
                BankMatchEvent.reverses_id.is_(None),
            )
        )
    )
    if existing:
        if dry_run:
            raise ConflictError("bank match group already exists; use a new preview group")
        if {(e.statement_entry_id, e.instrument_id, e.amount) for e in existing} != {
            (p.statement_entry_id, p.instrument_id, exact_decimal(p.amount)) for p in body.parts
        }:
            raise ConflictError("bank match group was already used for different allocations")
        return existing
    entry_ids = {part.statement_entry_id for part in body.parts}
    instrument_ids = {part.instrument_id for part in body.parts}
    entries = {
        row.id: row
        for row in await db.scalars(
            select(BankStatementEntry).where(
                BankStatementEntry.company_id == access.context.company_id,
                BankStatementEntry.id.in_(entry_ids),
            )
        )
    }
    instruments = {
        row.id: row
        for row in await db.scalars(
            select(BankInstrument).where(
                BankInstrument.company_id == access.context.company_id,
                BankInstrument.id.in_(instrument_ids),
            )
        )
    }
    if len(entries) != len(entry_ids) or len(instruments) != len(instrument_ids):
        raise ConflictError("bank match source changed or is outside the company")
    imports = {
        row.id: row
        for row in await db.scalars(
            select(BankStatementImport).where(
                BankStatementImport.company_id == access.context.company_id,
                BankStatementImport.id.in_({e.import_id for e in entries.values()}),
            )
        )
    }
    lines = {
        row.id: row
        for row in await db.scalars(
            select(JournalLine).where(
                JournalLine.company_id == access.context.company_id,
                JournalLine.id.in_({i.journal_line_id for i in instruments.values()}),
            )
        )
    }
    active = await _active_events(db, access, entry_ids, instrument_ids)
    entry_used: dict[uuid.UUID, Decimal] = {}
    instrument_used: dict[uuid.UUID, Decimal] = {}
    for event in active:
        entry_used[event.statement_entry_id] = (
            entry_used.get(event.statement_entry_id, Decimal(0)) + event.amount
        )
        instrument_used[event.instrument_id] = (
            instrument_used.get(event.instrument_id, Decimal(0)) + event.amount
        )
    statements: list[MatchSource] = []
    books: list[MatchSource] = []
    for entry in entries.values():
        if imports[entry.import_id].status != "COMMITTED" or entry.review_status not in {
            "NEW",
            "ACCEPTED",
        }:
            raise ConflictError("statement row is not accepted bank evidence")
        closed = await db.scalar(
            select(BankReconciliationSession.id)
            .where(
                BankReconciliationSession.company_id == entry.company_id,
                BankReconciliationSession.account_id == entry.account_id,
                BankReconciliationSession.status == "FINALIZED",
                BankReconciliationSession.period_from <= entry.transaction_date,
                BankReconciliationSession.period_to >= entry.transaction_date,
            )
            .limit(1)
        )
        if closed:
            raise ConflictError("amend the finalized bank session before matching")
        policy = await active_policy(db, access, entry.account_id)
        if (
            policy
            and policy.require_separate_reviewer
            and imports[entry.import_id].created_by == access.actor.user_id
        ):
            raise ConflictError("bank match requires a different reviewer")
        statements.append(
            MatchSource(
                entry.id,
                entry.tenant_id,
                entry.company_id,
                entry.account_id,
                entry.currency,
                entry.side,
                entry.amount - entry_used.get(entry.id, Decimal(0)),
            )
        )
    for instrument in instruments.values():
        line = lines.get(instrument.journal_line_id)
        if (
            line is None
            or line.account_id != instrument.account_id
            or line.currency != instrument.currency
            or line.amount != instrument.amount
        ):
            raise ConflictError("bank instrument differs from its book journal line")
        journal = await company_object(
            db, Journal, line.journal_id, company_id=access.context.company_id
        )
        reversed_journal = await db.scalar(
            select(Journal.id)
            .where(
                Journal.company_id == access.context.company_id,
                Journal.reversal_of_id == journal.id,
                Journal.status == "POSTED",
            )
            .limit(1)
        )
        latest = await db.scalar(
            select(BankInstrumentEvent)
            .where(
                BankInstrumentEvent.company_id == access.context.company_id,
                BankInstrumentEvent.instrument_id == instrument.id,
            )
            .order_by(BankInstrumentEvent.id.desc())
            .limit(1)
        )
        if (
            journal.status != "POSTED"
            or reversed_journal
            or latest is None
            or latest.action == "REVERSED"
        ):
            raise ConflictError("bank instrument is not an active posted book movement")
        profile = await db.scalar(
            select(AccountBankProfile).where(
                AccountBankProfile.company_id == access.context.company_id,
                AccountBankProfile.account_id == instrument.account_id,
            )
        )
        if (
            profile
            and profile.reconciliation_start_date
            and latest.action in {"CLEARED", "RECONCILED"}
            and latest.event_date < profile.reconciliation_start_date
        ):
            raise ConflictError("pre-cutover cleared instrument is not an open bank match")
        side = "CREDIT" if line.side == "DEBIT" else "DEBIT"
        books.append(
            MatchSource(
                instrument.id,
                instrument.tenant_id,
                instrument.company_id,
                instrument.account_id,
                instrument.currency,
                side,
                instrument.amount - instrument_used.get(instrument.id, Decimal(0)),
            )
        )
    assessment = preview(
        tuple(statements),
        tuple(books),
        tuple(MatchPart(p.statement_entry_id, p.instrument_id, p.amount) for p in body.parts),
    )
    if dry_run:
        return assessment
    result = []
    for part in body.parts:
        entry = entries[part.statement_entry_id]
        row = new(
            access,
            BankMatchEvent,
            statement_entry_id=entry.id,
            instrument_id=part.instrument_id,
            amount=exact_decimal(part.amount),
            bank_date=entry.transaction_date,
            group_id=body.group_id,
            reverses_id=None,
            reason=body.reason,
        )
        db.add(row)
        result.append(row)
        audit(db, access, row, "match", body.reason)
    await db.flush()
    return result


async def unmatch(
    db: AsyncSession, access: Access, match_id: uuid.UUID, reason: str
) -> BankMatchEvent:
    authorize(access, write=True, scope="accounting.bank_match.manage")
    await setup_lock(db, access)
    original = await company_object(
        db, BankMatchEvent, match_id, company_id=access.context.company_id
    )
    if original.reverses_id:
        raise ConflictError("a reversal cannot be unmatched")
    existing = await db.scalar(
        select(BankMatchEvent).where(
            BankMatchEvent.company_id == access.context.company_id,
            BankMatchEvent.reverses_id == original.id,
        )
    )
    if existing:
        return existing
    closed = await db.scalar(
        select(BankReconciliationSession.id)
        .where(
            BankReconciliationSession.company_id == access.context.company_id,
            BankReconciliationSession.account_id
            == (
                select(BankStatementEntry.account_id)
                .where(BankStatementEntry.id == original.statement_entry_id)
                .scalar_subquery()
            ),
            BankReconciliationSession.status == "FINALIZED",
            BankReconciliationSession.period_from <= original.bank_date,
            BankReconciliationSession.period_to >= original.bank_date,
        )
        .limit(1)
    )
    if closed:
        raise ConflictError("amend the finalized bank session before unmatching")
    row = new(
        access,
        BankMatchEvent,
        statement_entry_id=original.statement_entry_id,
        instrument_id=original.instrument_id,
        amount=original.amount,
        bank_date=original.bank_date,
        group_id=original.group_id,
        reverses_id=original.id,
        reason=reason,
    )
    db.add(row)
    await db.flush()
    audit(db, access, row, "unmatch", reason)
    return row


async def prepare_proposal(
    db: AsyncSession, access: Access, body: ProposalCreate
) -> BankAdjustmentProposal:
    """Record a bank-only exception; the ordinary voucher path remains the money owner."""
    authorize(access, write=True, scope="accounting.statement.review")
    await setup_lock(db, access)
    entry = await company_object(
        db, BankStatementEntry, body.statement_entry_id, company_id=access.context.company_id
    )
    imported = await company_object(
        db, BankStatementImport, entry.import_id, company_id=access.context.company_id
    )
    if imported.status != "COMMITTED" or entry.review_status not in {"NEW", "ACCEPTED"}:
        raise ConflictError("only reviewed bank statement rows can create an adjustment proposal")
    if (entry.side == "DEBIT" and body.kind == "RECEIPT") or (
        entry.side == "CREDIT" and body.kind == "PAYMENT"
    ):
        raise ValidationFailedError("proposed voucher direction differs from the bank row")
    await bank_account(db, access, entry.account_id, entry.currency)
    existing = await db.scalar(
        select(BankAdjustmentProposal).where(
            BankAdjustmentProposal.company_id == access.context.company_id,
            BankAdjustmentProposal.statement_entry_id == entry.id,
        )
    )
    if existing:
        if existing.kind != body.kind or existing.reason != body.reason:
            raise ConflictError("statement row already has a different adjustment proposal")
        return existing
    closed = await db.scalar(
        select(BankReconciliationSession.id).where(
            BankReconciliationSession.company_id == access.context.company_id,
            BankReconciliationSession.account_id == entry.account_id,
            BankReconciliationSession.status == "FINALIZED",
            BankReconciliationSession.period_from <= entry.transaction_date,
            BankReconciliationSession.period_to >= entry.transaction_date,
        )
    )
    if closed:
        raise ConflictError("amend the finalized bank session before preparing an adjustment")
    active = await _active_events(db, access, {entry.id}, set())
    remaining = entry.amount - sum((e.amount for e in active), Decimal(0))
    if remaining <= 0:
        raise ConflictError("statement row is already fully matched")
    row = new(
        access,
        BankAdjustmentProposal,
        statement_entry_id=entry.id,
        account_id=entry.account_id,
        kind=body.kind,
        amount=remaining,
        currency=entry.currency,
        status="PREPARED",
        voucher_id=None,
        reason=body.reason,
        decision_reason=None,
    )
    db.add(row)
    await db.flush()
    audit(db, access, row, "prepare", body.reason)
    return row


async def decide_proposal(
    db: AsyncSession,
    access: Access,
    proposal_id: uuid.UUID,
    decision: Literal["REJECTED", "RESOLVED"],
    body: ProposalDecision,
) -> BankAdjustmentProposal:
    authorize(access, write=True, scope="accounting.statement.review")
    await setup_lock(db, access)
    row = await company_object(
        db, BankAdjustmentProposal, proposal_id, company_id=access.context.company_id
    )
    if row.status == decision:
        if row.voucher_id != body.voucher_id or row.decision_reason != body.reason:
            raise ConflictError("adjustment proposal was already decided differently")
        return row
    if row.status != "PREPARED":
        raise ConflictError("adjustment proposal already has a terminal decision")
    entry = await company_object(
        db, BankStatementEntry, row.statement_entry_id, company_id=access.context.company_id
    )
    closed = await db.scalar(
        select(BankReconciliationSession.id).where(
            BankReconciliationSession.company_id == access.context.company_id,
            BankReconciliationSession.account_id == row.account_id,
            BankReconciliationSession.status == "FINALIZED",
            BankReconciliationSession.period_from <= entry.transaction_date,
            BankReconciliationSession.period_to >= entry.transaction_date,
        )
    )
    if closed:
        raise ConflictError("amend the finalized bank session before deciding an adjustment")
    if decision == "REJECTED":
        if body.voucher_id:
            raise ValidationFailedError("rejected proposal cannot reference a voucher")
    else:
        if not body.voucher_id:
            raise ValidationFailedError("resolved proposal requires a posted voucher")
        intent = await db.scalar(
            select(VoucherMoneyIntent).where(
                VoucherMoneyIntent.company_id == access.context.company_id,
                VoucherMoneyIntent.voucher_id == body.voucher_id,
                VoucherMoneyIntent.status == "COMMITTED",
                VoucherMoneyIntent.kind == row.kind,
            )
        )
        if intent is None:
            raise ConflictError("proposal voucher has no committed matching money intent")
        instruments = list(
            await db.scalars(
                select(BankInstrument).where(
                    BankInstrument.company_id == access.context.company_id,
                    BankInstrument.intent_id == intent.id,
                    BankInstrument.account_id == row.account_id,
                    BankInstrument.currency == row.currency,
                )
            )
        )
        active = await _active_events(db, access, {entry.id}, {i.id for i in instruments})
        matched = sum(
            (
                e.amount
                for e in active
                if e.statement_entry_id == entry.id
                and e.instrument_id in {i.id for i in instruments}
            ),
            Decimal(0),
        )
        if matched != row.amount:
            raise ConflictError("voucher bank movement must exactly cover the proposed remainder")
    guard_change(
        row, access, status=decision, voucher_id=body.voucher_id, decision_reason=body.reason
    )
    row.status = decision
    row.voucher_id = body.voucher_id
    row.decision_reason = body.reason
    row.updated_by = access.actor.user_id
    row.row_version += 1
    await db.flush()
    audit(db, access, row, decision.lower(), body.reason)
    return row


async def calculate_session(
    db: AsyncSession, access: Access, body: SessionCreate
) -> dict[str, Any]:
    account = await bank_account(db, access, body.account_id)
    policy = await active_policy(db, access, body.account_id)
    if body.period_from > body.period_to:
        raise ValidationFailedError("invalid bank reconciliation period")
    profile = await db.scalar(
        select(AccountBankProfile).where(
            AccountBankProfile.company_id == access.context.company_id,
            AccountBankProfile.account_id == account.id,
        )
    )
    assert profile is not None
    if profile.reconciliation_start_date is None:
        raise ConflictError("bank reconciliation cutover date is not configured")
    prior = await db.scalar(
        select(BankReconciliationSession)
        .where(
            BankReconciliationSession.company_id == access.context.company_id,
            BankReconciliationSession.account_id == account.id,
            BankReconciliationSession.status == "FINALIZED",
            BankReconciliationSession.period_to < body.period_from,
        )
        .order_by(BankReconciliationSession.period_to.desc())
        .limit(1)
    )
    if prior:
        if (
            prior.period_to + dt.timedelta(days=1) != body.period_from
            or prior.closing_balance != body.opening_balance
        ):
            raise ConflictError("statement opening does not chain from prior finalized session")
    elif profile.reconciliation_start_date != body.period_from:
        raise ConflictError("first statement period must start at the bank reconciliation cutover")
    imports = list(
        await db.scalars(
            select(BankStatementImport)
            .where(
                BankStatementImport.company_id == access.context.company_id,
                BankStatementImport.account_id == account.id,
                BankStatementImport.status == "COMMITTED",
                BankStatementImport.period_from >= body.period_from,
                BankStatementImport.period_to <= body.period_to,
            )
            .order_by(BankStatementImport.period_from, BankStatementImport.id)
        )
    )
    if (
        not imports
        or imports[0].period_from != body.period_from
        or imports[-1].period_to != body.period_to
    ):
        raise ConflictError("committed statements do not cover the full session period")
    for left, right in pairwise(imports):
        if (
            left.period_to + dt.timedelta(days=1) != right.period_from
            or left.closing_balance != right.opening_balance
        ):
            raise ConflictError("statement imports overlap, gap or have a broken balance chain")
    if (
        imports[0].opening_balance != body.opening_balance
        or imports[-1].closing_balance != body.closing_balance
    ):
        raise ConflictError("session balances differ from the reviewed statement chain")
    entries = list(
        await db.scalars(
            select(BankStatementEntry).where(
                BankStatementEntry.company_id == access.context.company_id,
                BankStatementEntry.import_id.in_([row.id for row in imports]),
            )
        )
    )
    included = [row for row in entries if row.review_status in {"NEW", "ACCEPTED"}]
    ambiguous = sum(row.review_status == "AMBIGUOUS" for row in entries)
    matches = await _active_events(db, access, {row.id for row in included}, set())
    by_row: dict[uuid.UUID, Decimal] = {}
    for event in matches:
        by_row[event.statement_entry_id] = (
            by_row.get(event.statement_entry_id, Decimal(0)) + event.amount
        )
    uncovered = [row for row in included if by_row.get(row.id, Decimal(0)) != row.amount]
    movement = sum(
        (row.amount if row.side == "CREDIT" else -row.amount for row in included), Decimal(0)
    )
    book_rows = list(
        (
            await db.execute(
                select(JournalLine.side, JournalLine.amount)
                .join(Journal, JournalLine.journal_id == Journal.id)
                .where(
                    JournalLine.company_id == access.context.company_id,
                    JournalLine.account_id == account.id,
                    JournalLine.component == "PRINCIPAL",
                    Journal.status == "POSTED",
                    Journal.posting_date <= body.period_to,
                )
            )
        ).all()
    )
    book_balance = sum(
        (amount if side == "DEBIT" else -amount for side, amount in book_rows), Decimal(0)
    )
    instruments = list(
        await db.scalars(
            select(BankInstrument).where(
                BankInstrument.company_id == access.context.company_id,
                BankInstrument.account_id == account.id,
                BankInstrument.booking_date <= body.period_to,
            )
        )
    )
    missing_opening = 0
    historical_events = list(
        await db.scalars(
            select(BankInstrumentEvent)
            .where(
                BankInstrumentEvent.company_id == access.context.company_id,
                BankInstrumentEvent.instrument_id.in_({i.id for i in instruments}),
                BankInstrumentEvent.event_date < profile.reconciliation_start_date,
            )
            .order_by(BankInstrumentEvent.event_date, BankInstrumentEvent.id)
        )
    )
    latest_historical: dict[uuid.UUID, str] = {
        event.instrument_id: event.action for event in historical_events
    }
    if prior is None:
        opening_ids = set(
            await db.scalars(
                select(BankOpeningItem.instrument_id).where(
                    BankOpeningItem.company_id == access.context.company_id,
                    BankOpeningItem.account_id == account.id,
                    BankOpeningItem.cutoff_date == body.period_from,
                )
            )
        )
        missing_opening = sum(
            instrument.booking_date < body.period_from
            and instrument.id not in opening_ids
            and latest_historical.get(instrument.id) not in {"CLEARED", "RECONCILED", "REVERSED"}
            for instrument in instruments
        )
    instrument_events = await _active_events(db, access, set(), {i.id for i in instruments})
    bank_events = list(
        await db.scalars(
            select(BankInstrumentEvent).where(
                BankInstrumentEvent.company_id == access.context.company_id,
                BankInstrumentEvent.instrument_id.in_({i.id for i in instruments}),
                BankInstrumentEvent.event_date <= body.period_to,
            )
        )
    )
    used: dict[uuid.UUID, Decimal] = {}
    for event in instrument_events:
        if event.bank_date <= body.period_to:
            used[event.instrument_id] = used.get(event.instrument_id, Decimal(0)) + event.amount
    for instrument in instruments:
        if latest_historical.get(instrument.id) in {"CLEARED", "RECONCILED"}:
            if used.get(instrument.id, Decimal(0)):
                raise ConflictError("pre-cutover cleared instrument also has a statement match")
            used[instrument.id] = instrument.amount
    instrument_ids = {i.journal_line_id for i in instruments}
    duplicate_instruments = len(instruments) - len(instrument_ids)
    book_line_ids = set(
        await db.scalars(
            select(JournalLine.id)
            .join(Journal, JournalLine.journal_id == Journal.id)
            .where(
                JournalLine.company_id == access.context.company_id,
                JournalLine.account_id == account.id,
                JournalLine.component == "PRINCIPAL",
                Journal.status == "POSTED",
                Journal.posting_date <= body.period_to,
            )
        )
    )
    uncovered_book_lines = len(book_line_ids - instrument_ids)
    line_sides: dict[uuid.UUID, str] = dict(
        (
            await db.execute(
                select(JournalLine.id, JournalLine.side).where(
                    JournalLine.company_id == access.context.company_id,
                    JournalLine.id.in_(instrument_ids),
                )
            )
        )
        .tuples()
        .all()
    )
    outstanding = sum(
        (
            (i.amount - used.get(i.id, Decimal(0)))
            * (1 if line_sides[i.journal_line_id] == "DEBIT" else -1)
            for i in instruments
        ),
        Decimal(0),
    )
    expected = book_balance - outstanding
    source = {
        "imports": [[str(row.id), row.file_sha256, row.row_version] for row in imports],
        "entries": sorted(
            [str(row.id), row.row_sha256, row.review_status, row.row_version] for row in entries
        ),
        "matches": [
            [str(row.id), str(row.statement_entry_id), str(row.instrument_id), str(row.amount)]
            for row in instrument_events
        ],
        "book_lines": sorted(str(identity) for identity in book_line_ids),
        "instruments": sorted(
            [str(row.id), str(row.journal_line_id), str(row.amount)] for row in instruments
        ),
        "precleared_instruments": sorted(
            str(row.id)
            for row in instruments
            if latest_historical.get(row.id) in {"CLEARED", "RECONCILED"}
        ),
        "bank_events": sorted(
            [str(event.id), str(event.instrument_id), event.action, event.event_date.isoformat()]
            for event in bank_events
        ),
    }
    source_sha256 = hashlib.sha256(canonical_json(source)).hexdigest()
    balance_agrees = (
        expected == body.closing_balance and body.opening_balance + movement == body.closing_balance
    )
    rows_covered = (
        not ambiguous
        and not uncovered
        and not uncovered_book_lines
        and not missing_opening
        and not duplicate_instruments
    )
    return {
        "balance_agrees": balance_agrees,
        "rows_covered": rows_covered,
        "exception_open": not rows_covered or not balance_agrees,
        "statement_row_count": len(included),
        "uncovered_statement_rows": len(uncovered),
        "unreviewed_duplicates": ambiguous,
        "uncovered_book_lines": uncovered_book_lines,
        "missing_opening_items": missing_opening,
        "duplicate_book_instruments": duplicate_instruments,
        "book_balance": str(book_balance),
        "outstanding_book_amount": str(outstanding),
        "expected_statement_balance": str(expected),
        "statement_movement": str(movement),
        "source_sha256": source_sha256,
        "policy_revision_id": str(policy.id) if policy else None,
        "import_ids": [str(row.id) for row in imports],
        "entry_ids": sorted(str(row.id) for row in included),
        "instrument_ids": sorted(str(row.id) for row in instruments),
        "precleared_instrument_ids": source["precleared_instruments"],
        "match_ids": [str(row.id) for row in instrument_events],
    }


async def create_session(
    db: AsyncSession, access: Access, body: SessionCreate
) -> BankReconciliationSession:
    authorize(access, write=True, scope="accounting.statement.review")
    await setup_lock(db, access)
    account = await bank_account(db, access, body.account_id)
    conflicting_final = await db.scalar(
        select(BankReconciliationSession.id)
        .where(
            BankReconciliationSession.company_id == access.context.company_id,
            BankReconciliationSession.account_id == body.account_id,
            BankReconciliationSession.status == "FINALIZED",
            BankReconciliationSession.period_to >= body.period_from,
        )
        .limit(1)
    )
    if conflicting_final:
        raise ConflictError(
            "amend the finalized bank chain before creating an overlapping or earlier session"
        )
    snapshot = await calculate_session(db, access, body)
    draft = await db.scalar(
        select(BankReconciliationSession)
        .where(
            BankReconciliationSession.company_id == access.context.company_id,
            BankReconciliationSession.account_id == body.account_id,
            BankReconciliationSession.period_from == body.period_from,
            BankReconciliationSession.period_to == body.period_to,
            BankReconciliationSession.status == "DRAFT",
        )
        .order_by(BankReconciliationSession.generation.desc())
        .limit(1)
    )
    if (
        draft is not None
        and draft.opening_balance == body.opening_balance
        and draft.closing_balance == body.closing_balance
        and draft.snapshot == snapshot
    ):
        return draft
    existing = await db.scalar(
        select(BankReconciliationSession).where(
            BankReconciliationSession.company_id == access.context.company_id,
            BankReconciliationSession.account_id == body.account_id,
            BankReconciliationSession.period_from == body.period_from,
            BankReconciliationSession.period_to == body.period_to,
            BankReconciliationSession.status == "FINALIZED",
        )
    )
    if existing:
        raise ConflictError("bank session is already finalized; amend it explicitly")
    generation = await db.scalar(
        select(func.max(BankReconciliationSession.generation)).where(
            BankReconciliationSession.company_id == access.context.company_id,
            BankReconciliationSession.account_id == body.account_id,
            BankReconciliationSession.period_from == body.period_from,
            BankReconciliationSession.period_to == body.period_to,
        )
    )
    row = new(
        access,
        BankReconciliationSession,
        account_id=body.account_id,
        currency=account.currency or access.context.base_currency,
        period_from=body.period_from,
        period_to=body.period_to,
        generation=(generation or 0) + 1,
        opening_balance=exact_decimal(body.opening_balance),
        closing_balance=exact_decimal(body.closing_balance),
        status="DRAFT",
        snapshot=snapshot,
        reason=body.reason,
    )
    db.add(row)
    await db.flush()
    audit(db, access, row, "draft", body.reason)
    return row


async def finalize_session(
    db: AsyncSession, access: Access, session_id: uuid.UUID, reason: str
) -> BankReconciliationSession:
    authorize(access, write=True, scope="accounting.bank_session.finalize")
    await setup_lock(db, access)
    row = await company_object(
        db, BankReconciliationSession, session_id, company_id=access.context.company_id
    )
    if row.status == "FINALIZED":
        return row
    if row.status != "DRAFT":
        raise ConflictError("bank session cannot be finalized")
    conflicting_final = await db.scalar(
        select(BankReconciliationSession.id)
        .where(
            BankReconciliationSession.company_id == access.context.company_id,
            BankReconciliationSession.account_id == row.account_id,
            BankReconciliationSession.status == "FINALIZED",
            BankReconciliationSession.period_to >= row.period_from,
        )
        .limit(1)
    )
    if conflicting_final:
        raise ConflictError("bank session overlaps or precedes an already finalized period")
    policy = await active_policy(db, access, row.account_id)
    if policy and policy.require_separate_reviewer and row.created_by == access.actor.user_id:
        raise ConflictError("bank session requires a different final reviewer")
    current = await calculate_session(
        db,
        access,
        SessionCreate(
            account_id=row.account_id,
            period_from=row.period_from,
            period_to=row.period_to,
            opening_balance=row.opening_balance,
            closing_balance=row.closing_balance,
            reason=reason,
        ),
    )
    if current != row.snapshot:
        raise ConflictError("bank source changed after session review; create a fresh draft")
    if not current["balance_agrees"] or not current["rows_covered"]:
        raise ConflictError("bank balance or statement/book row coverage is incomplete")
    guard_change(row, access, status="FINALIZED", reason=reason)
    row.status = "FINALIZED"
    row.reason = reason
    row.row_version += 1
    row.updated_by = access.actor.user_id
    audit(db, access, row, "finalize", reason)
    return row


async def amend_session(
    db: AsyncSession, access: Access, session_id: uuid.UUID, reason: str
) -> BankReconciliationSession:
    authorize(access, write=True, scope="accounting.bank_session.finalize")
    await setup_lock(db, access)
    row = await company_object(
        db, BankReconciliationSession, session_id, company_id=access.context.company_id
    )
    if row.status != "FINALIZED":
        if row.status == "AMENDED" and row.reason == reason:
            return row
        raise ConflictError("only a finalized bank session may be amended")
    later = await db.scalar(
        select(BankReconciliationSession.id)
        .where(
            BankReconciliationSession.company_id == row.company_id,
            BankReconciliationSession.account_id == row.account_id,
            BankReconciliationSession.status == "FINALIZED",
            BankReconciliationSession.period_from > row.period_to,
        )
        .limit(1)
    )
    if later:
        raise ConflictError(
            "amend later finalized bank periods first to preserve the balance chain"
        )
    guard_change(row, access, status="AMENDED", reason=reason)
    row.status = "AMENDED"
    row.reason = reason
    row.row_version += 1
    row.updated_by = access.actor.user_id
    audit(db, access, row, "amend", reason)
    return row
