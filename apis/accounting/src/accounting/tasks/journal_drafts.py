"""Journal draft validation and local writes; posting has a separate reservation boundary."""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal, cast

from billing_platform.db.access import company_object
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.idempotency import CommandResult, canonical_json
from billing_platform.ids import uuid7
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.ledger import Entry, ValuedEntry, value_entries
from accounting.domain.reference import validate_reference
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import Account
from accounting.resources import BY_NAME
from accounting.schemas.ledger import (
    JournalCreate,
    JournalLineCreate,
    JournalPreview,
    JournalPreviewLine,
    JournalUpdate,
)
from accounting.tasks.access import authorize, readable, writable
from accounting.tasks.commands import audit, values_of
from accounting.tasks.exchange_rates import approved_for, previously_reviewed
from accounting.tasks.financial_commands import (
    FinancialEffect,
    financial_command,
    financial_context,
)
from accounting.tasks.fiscal import setup

if TYPE_CHECKING:
    from accounting.tasks.voucher_tax import Outcome


async def lines(
    db: AsyncSession, company_id: uuid.UUID, journal_id: uuid.UUID
) -> list[JournalLine]:
    result = list(
        await db.scalars(
            select(JournalLine)
            .where(
                JournalLine.company_id == company_id,
                JournalLine.journal_id == journal_id,
            )
            .order_by(JournalLine.sequence)
            .limit(201)
        )
    )
    if not 2 <= len(result) <= 200:
        raise ConflictError("journal line set is incomplete")
    return result


def line_input(line: JournalLine, *, opening: bool = False) -> JournalLineCreate:
    return JournalLineCreate(
        account_id=line.account_id,
        side=cast(Literal["DEBIT", "CREDIT"], line.side),
        currency=line.currency,
        amount=line.amount,
        exchange_rate=line.exchange_rate,
        description=line.description,
        opening_base_amount=line.base_amount if opening else None,
    )


def source_hash(body: JournalCreate, kind: str, reversal_of_id: uuid.UUID | None) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                # Untaxed bodies keep their pre-Phase-8 fingerprint for source replays.
                "body": body.model_dump(
                    mode="json",
                    exclude={"expected_version", "tax"}
                    if body.tax is None
                    else {"expected_version"},
                ),
                "kind": kind,
                "reversal_of_id": str(reversal_of_id) if reversal_of_id else None,
            }
        )
    ).hexdigest()


async def validate_lines(
    db: AsyncSession,
    access: Access,
    body: JournalCreate,
    *,
    kind: str,
    exempt: frozenset[uuid.UUID] = frozenset(),
) -> tuple[tuple[ValuedEntry, ...], dict[uuid.UUID, Account]]:
    """``exempt`` names accounts reached only by generated tax lines of a manual journal."""
    facts = financial_context(access)
    if kind not in {"OPENING", "REVERSAL"} and any(
        line.opening_base_amount is not None for line in body.lines
    ):
        raise ValidationFailedError("explicit carrying values are restricted to opening migrations")
    await setup(db, access)
    if body.posting_date < facts.books_begin_date:
        raise ValidationFailedError("posting date precedes books begin date")
    account_spec = BY_NAME["account"]
    authorize(access, account_spec, "read")
    ids = {line.account_id for line in body.lines}
    accounts = {row.id: row for row in await db.scalars(select(Account).where(Account.id.in_(ids)))}
    if set(accounts) != ids:
        raise NotFoundError("posting account not found")
    required = {
        "id",
        "kind",
        "status",
        "party_id",
        "party_role",
        "currency_mode",
        "currency",
        "posting_policy",
    }
    for row in accounts.values():
        if row.company_id != access.context.company_id:
            raise PermissionDeniedError("posting account is outside the requested company")
        if not required <= readable(access, account_spec, values_of(row, account_spec)):
            raise PermissionDeniedError("posting account attributes are not readable")
        if row.status != "ACTIVE" and kind != "REVERSAL":
            raise ConflictError("posting account must be active")
        if (
            kind == "MANUAL"
            and row.id not in exempt
            and (row.posting_policy != "MANUAL_ALLOWED" or row.kind == "PARTY")
        ):
            raise ConflictError("this account requires its source or subledger workflow")
    currencies = {line.currency for line in body.lines}
    validate_reference(None, None, list(currencies))
    if (
        currencies - {access.context.base_currency}
        and "multi_currency" not in access.context.features
    ):
        raise ConflictError("foreign currency posting requires multi_currency")
    if currencies - {access.context.base_currency} - access.context.allowed_currencies:
        raise ConflictError("journal currency is not enabled for this company")
    for line in body.lines:
        account = accounts[line.account_id]
        expected = (
            access.context.base_currency
            if account.currency_mode == "BASE"
            else account.currency
            if account.currency_mode == "FIXED"
            else None
        )
        if expected is not None and line.currency != expected:
            raise ValidationFailedError("journal currency differs from its account")
        if kind == "MANUAL" and line.currency != access.context.base_currency:
            quote = await approved_for(
                db,
                access.context.company_id,
                line.currency,
                access.context.base_currency,
                "ACCOUNTING",
                body.posting_date,
            )
            if quote is not None and quote.rate != line.exchange_rate:
                raise ConflictError("journal rate differs from the approved accounting quote")
            if quote is None and await previously_reviewed(
                db,
                access.context.company_id,
                line.currency,
                access.context.base_currency,
                "ACCOUNTING",
                body.posting_date,
            ):
                raise ConflictError("the reviewed accounting quote was withdrawn")
    valued = value_entries(
        tuple(
            Entry(line.account_id, line.side, line.currency, line.amount, line.exchange_rate)
            for line in body.lines
        ),
        access.context.base_currency,
        facts.amount_precision,
        facts.rounding_mode,
        opening_values=tuple(line.opening_base_amount for line in body.lines),
    )
    return valued, accounts


def require_preview_fields(access: Access) -> None:
    for name, required in {
        "journal": {"base_currency", "total_debit", "total_credit"},
        "journal_line": {
            "account_id",
            "side",
            "currency",
            "amount",
            "exchange_rate",
            "base_currency",
            "base_amount",
        },
    }.items():
        spec = FINANCIAL_BY_NAME[name]
        authorize(access, spec, "read")
        if not required <= readable(access, spec):
            raise PermissionDeniedError("calculation inputs are not readable")


async def preview(db: AsyncSession, access: Access, body: JournalCreate) -> JournalPreview:
    if body.tax is not None:
        raise ValidationFailedError("preview taxed journals through voucher-tax-previews")
    require_preview_fields(access)
    valued, _ = await validate_lines(db, access, body, kind="MANUAL")
    total = sum((item.base_amount for item in valued if item.entry.side == "DEBIT"), Decimal(0))
    return JournalPreview(
        base_currency=access.context.base_currency,
        total_debit=total,
        total_credit=total,
        lines=[
            JournalPreviewLine(
                sequence=index,
                account_id=item.entry.account_id,
                side=cast(Literal["DEBIT", "CREDIT"], item.entry.side),
                currency=item.entry.currency,
                amount=item.entry.amount,
                exchange_rate=item.entry.exchange_rate,
                base_currency=access.context.base_currency,
                base_amount=item.base_amount,
            )
            for index, item in enumerate(valued, 1)
        ],
    )


async def write_lines(
    db: AsyncSession,
    access: Access,
    row: Journal,
    body: JournalCreate,
    valued: tuple[ValuedEntry, ...],
    accounts: dict[uuid.UUID, Account],
) -> None:
    spec = FINANCIAL_BY_NAME["journal_line"]
    for index, (incoming, value) in enumerate(zip(body.lines, valued, strict=True), 1):
        writable(access, spec, {}, incoming.model_dump())
        account = accounts[incoming.account_id]
        values: dict[str, Any] = incoming.model_dump(exclude={"opening_base_amount"}) | {
            "journal_id": row.id,
            "sequence": index,
            "base_currency": row.base_currency,
            "base_amount": value.base_amount,
            "party_id": account.party_id,
            "role": account.party_role,
        }
        changed = writable(access, spec, {}, values)
        line = JournalLine(
            id=uuid7(),
            tenant_id=access.actor.tenant_id,
            company_id=row.company_id,
            created_by=access.actor.user_id,
            updated_by=access.actor.user_id,
            **values,
        )
        db.add(line)
        await db.flush()
        audit(db, access, spec, line, "create", changed)


async def create_in_transaction(
    db: AsyncSession,
    access: Access,
    body: JournalCreate,
    *,
    kind: str,
    source_system: str,
    source_type: str,
    source_id: str,
    reversal_of_id: uuid.UUID | None = None,
    tax: Outcome | None = None,
) -> Journal:
    """Called only under the company lock by an authorized domain workflow.

    ``tax`` is a ready analysis; its lines (entered plus generated) are written and its
    evidence row is stored with a new journal.
    """
    from accounting.tasks.fiscal import posting_period

    await posting_period(db, access, body.posting_date)
    spec = FINANCIAL_BY_NAME["journal"]
    fingerprint = source_hash(body, kind, reversal_of_id)
    existing = await db.scalar(
        select(Journal).where(
            Journal.company_id == access.context.company_id,
            Journal.source_system == source_system,
            Journal.source_type == source_type,
            Journal.source_id == source_id,
        )
    )
    if existing is not None:
        if existing.source_hash != fingerprint:
            raise ConflictError("source identity was reused with different journal content")
        return existing
    written = body if tax is None else tax.draft(body)
    valued, accounts = await validate_lines(
        db, access, written, kind=kind, exempt=generated(tax, body)
    )
    total = sum((item.base_amount for item in valued if item.entry.side == "DEBIT"), Decimal(0))
    values = {
        "kind": kind,
        "status": "DRAFT",
        "document_date": body.document_date,
        "posting_date": body.posting_date,
        "description": body.description,
        "base_currency": access.context.base_currency,
        "total_debit": total,
        "total_credit": total,
        "source_system": source_system,
        "source_type": source_type,
        "source_id": source_id,
        "source_hash": fingerprint,
        "configuration_hash": financial_context(access).configuration_hash,
        "features": [],
        "reversal_of_id": reversal_of_id,
    }
    changed = writable(
        access, spec, {}, values | {"lines": [line.model_dump() for line in written.lines]}
    )
    row = Journal(
        id=uuid7(),
        tenant_id=access.actor.tenant_id,
        company_id=access.context.company_id,
        created_by=access.actor.user_id,
        updated_by=access.actor.user_id,
        **values,
    )
    db.add(row)
    await db.flush()
    await write_lines(db, access, row, written, valued, accounts)
    audit(db, access, spec, row, "create", changed)
    if tax is not None:
        from accounting.tasks.finance_records import create_row

        await create_row(db, access, "journal_tax", journal_id=row.id, **tax.values)
    return row


def generated(tax: Outcome | None, body: JournalCreate) -> frozenset[uuid.UUID]:
    if tax is None:
        return frozenset()
    entered = {line.account_id for line in tax.lines[: tax.line_count]}
    return frozenset(line.account_id for line in tax.lines[tax.line_count :]) - entered


async def taxed(db: AsyncSession, access: Access, body: JournalCreate) -> Outcome | None:
    if body.tax is None:
        return None
    from accounting.tasks.fiscal import posting_period
    from accounting.tasks.voucher_tax import resolve_journal

    # A closed or locked period refuses before any tax master is read.
    await posting_period(db, access, body.posting_date)
    outcome = await resolve_journal(db, access, body)
    outcome.require_ready()
    return outcome


async def create(
    factory: async_sessionmaker[AsyncSession], access: Access, body: JournalCreate, key: str
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        outcome = await taxed(db, access, body)
        row = await create_in_transaction(
            db,
            access,
            body,
            kind="MANUAL",
            source_system="accounting",
            source_type="manual",
            source_id=str(uuid7()),
            tax=outcome,
        )
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["journal"],
        "create",
        body,
        key,
        mutate,
        permission="ledger.post_journal",
        status=201,
    )


async def update(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    object_id: uuid.UUID,
    body: JournalUpdate,
    key: str,
) -> CommandResult[BaseModel]:
    spec = FINANCIAL_BY_NAME["journal"]

    async def mutate(db: AsyncSession) -> FinancialEffect:
        row = await company_object(db, Journal, object_id, company_id=access.context.company_id)
        if (
            row.kind != "MANUAL"
            or row.status != "DRAFT"
            or row.row_version != body.expected_version
        ):
            raise ConflictError("only a current manual draft can be edited")
        previous = await lines(db, row.company_id, row.id)
        before = values_of(row, spec) | {
            "lines": [line_input(line).model_dump() for line in previous]
        }
        from accounting.tasks.voucher_tax import stored

        evidence = await stored(db, row)
        if (evidence is None) != (body.tax is None):
            raise ConflictError("tax cannot be added to or removed from a draft; void it instead")
        outcome = await taxed(db, access, body)
        written = body if outcome is None else outcome.draft(body)
        valued, accounts = await validate_lines(
            db, access, written, kind=row.kind, exempt=generated(outcome, body)
        )
        total = sum((item.base_amount for item in valued if item.entry.side == "DEBIT"), Decimal(0))
        incoming = {
            "document_date": body.document_date,
            "posting_date": body.posting_date,
            "description": body.description,
            "base_currency": access.context.base_currency,
            "total_debit": total,
            "total_credit": total,
            "source_hash": source_hash(body, row.kind, None),
            "configuration_hash": financial_context(access).configuration_hash,
        }
        changed = writable(
            access,
            spec,
            before,
            before | incoming | {"lines": [line.model_dump() for line in written.lines]},
        )
        for line in previous:
            # Draft-only children; immutable posted lines never reach this path.
            await db.delete(line)
        await db.flush()
        for field, value in incoming.items():
            setattr(row, field, value)
        row.row_version += 1
        row.updated_by = access.actor.user_id
        await write_lines(db, access, row, written, valued, accounts)
        audit(db, access, spec, row, "update", changed)
        if outcome is not None and evidence is not None:
            from accounting.tasks.finance_records import change_row

            await change_row(db, access, "journal_tax", evidence, "update", **outcome.values)
        return FinancialEffect(row)

    return await financial_command(
        factory,
        access,
        spec,
        "update",
        body,
        key,
        mutate,
        permission="ledger.post_journal",
        object_id=object_id,
    )
