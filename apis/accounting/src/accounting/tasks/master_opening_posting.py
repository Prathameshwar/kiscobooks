"""Complete a master opening through the native ledger, outside its creation transaction."""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.db.access import company_object
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PlatformError
from identity_posting import PostingClient, ReservationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.financial_opening import execution_chunks
from accounting.models.ledger import Journal, JournalLine
from accounting.models.master_opening import MasterOpeningBalance
from accounting.models.masters import Account, AccountGroup, AccountHead
from accounting.models.subledger import OpeningBatch
from accounting.schemas.financial_opening import OpeningEntry
from accounting.schemas.ledger import JournalCreate
from accounting.schemas.masters import ExpectedVersion
from accounting.tasks.finance_records import change_row, require_fields
from accounting.tasks.financial_commands import financial_context


def company_batches() -> Any:
    """Additive master batches must never hide or replace the company declaration."""
    return (
        ~select(MasterOpeningBalance.id)
        .where(
            MasterOpeningBalance.company_id == OpeningBatch.company_id,
            MasterOpeningBalance.id == OpeningBatch.id,
        )
        .correlate(OpeningBatch)
        .exists()
    )


def require_posting(current: Access) -> None:
    for permission in ("ledger.post_journal", "period.post"):
        current.actor.require_scope(
            permission, target=ScopePath(company_id=current.context.company_id)
        )


async def offset_account(db: AsyncSession, current: Access, row: MasterOpeningBalance) -> Account:
    offset = await db.scalar(
        select(Account).where(
            Account.company_id == row.company_id, Account.code == "OPENING_BALANCE_OFFSET"
        )
    )
    if offset is None:
        raise ConflictError("opening-balance offset account is unavailable")
    require_fields(
        current,
        "account",
        {"kind", "status", "currency_mode", "posting_policy", "group_id", "inventory_affected"},
        row=offset,
    )
    group = await company_object(db, AccountGroup, offset.group_id, company_id=row.company_id)
    require_fields(current, "account_group", {"head_id"}, row=group)
    head = await company_object(db, AccountHead, group.head_id, company_id=row.company_id)
    require_fields(current, "account_head", {"nature"}, row=head)
    if (
        offset.id == row.account_id
        or offset.kind != "GENERAL"
        or offset.status != "ACTIVE"
        or offset.currency_mode != "BASE"
        or offset.posting_policy != "MANUAL_ALLOWED"
        or offset.inventory_affected
        or head.nature != "EQUITY"
    ):
        raise ConflictError("configure an active equity opening-balance offset account")
    return offset


async def prepare(db: AsyncSession, current: Access, row: MasterOpeningBalance) -> None:
    from accounting.tasks.financial_opening import require_capture_write
    from accounting.tasks.journal_drafts import create_in_transaction
    from accounting.tasks.master_opening import declaration
    from accounting.tasks.openings import preview, require_opening_revision_window
    from accounting.tasks.templates import seed_initial_chart

    require_posting(current)
    await require_opening_revision_window(db, current, row.opening_date)
    await seed_initial_chart(db, current)
    offset = await offset_account(db, current, row)
    value = OpeningEntry.model_validate(row.entry)
    if value.base_amount is None:
        raise ConflictError("master opening carrying value is missing")
    body = declaration(current, value, row.opening_date)
    body.entries.append(
        OpeningEntry(
            source_key="offset-" + row.id.hex,
            account_id=offset.id,
            side="CREDIT" if value.side == "DEBIT" else "DEBIT",
            currency=current.context.base_currency,
            amount=value.base_amount,
            base_amount=value.base_amount,
            exchange_rate=Decimal(1),
            description="Opening balance offset",
        )
    )
    await require_capture_write(db, current, body)
    facts = financial_context(current)
    plan = execution_chunks(
        body, current.context.base_currency, facts.amount_precision, facts.rounding_mode
    )[0]
    await preview(db, current, plan, master_opening_id=row.id)
    # Shared immutable identity makes the owner link explicit without mutable JSON markers.
    from accounting.financial_resources import FINANCIAL_BY_NAME
    from accounting.tasks.access import writable
    from accounting.tasks.commands import audit

    values = {
        "status": "DRAFT",
        "posting_date": plan.posting_date,
        "description": plan.description,
        "payload": plan.model_dump(mode="json"),
        "replacement_of_id": None,
        "journal_id": None,
        "finalized_at": None,
    }
    spec = FINANCIAL_BY_NAME["opening_batch"]
    changed = writable(current, spec, {}, values)
    batch = OpeningBatch(
        id=row.id,
        tenant_id=current.actor.tenant_id,
        company_id=row.company_id,
        created_by=current.actor.user_id,
        updated_by=current.actor.user_id,
        **values,
    )
    db.add(batch)
    await db.flush()
    audit(db, current, spec, batch, "create", changed)
    journal = await create_in_transaction(
        db,
        current,
        JournalCreate(
            document_date=plan.posting_date,
            posting_date=plan.posting_date,
            description=plan.description,
            lines=plan.lines,
        ),
        kind="OPENING",
        source_system="master-creation",
        source_type="opening",
        source_id=str(batch.id),
    )
    await change_row(db, current, "opening_batch", batch, "update", journal_id=journal.id)
    from accounting.tasks.journal_posting import prepare_in_transaction

    await prepare_in_transaction(db, current, journal.id, ExpectedVersion(expected_version=1))


async def before_post(
    db: AsyncSession, current: Access, journal: Journal, batch: OpeningBatch
) -> None:
    if journal.source_system != "master-creation":
        return
    row = await company_object(db, MasterOpeningBalance, batch.id, company_id=journal.company_id)
    if row.status != "POSTING" or journal.source_id != str(row.id):
        raise ConflictError("master opening source differs from its posting")
    offset = await offset_account(db, current, row)
    changed = await db.scalar(
        select(JournalLine.id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(
            JournalLine.company_id == row.company_id,
            JournalLine.journal_id == journal.id,
            (JournalLine.party_id.is_distinct_from(Account.party_id))
            | (JournalLine.role.is_distinct_from(Account.party_role)),
        )
        .limit(1)
    )
    offset_line = await db.scalar(
        select(JournalLine.account_id).where(
            JournalLine.company_id == row.company_id,
            JournalLine.journal_id == journal.id,
            JournalLine.sequence == 2,
        )
    )
    if changed or offset_line != offset.id:
        raise ConflictError("master opening account identity changed before posting")


async def complete(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    identity: uuid.UUID,
    client: PostingClient | None,
) -> None:
    from accounting.tasks.journal_posting import PostingDependencyError, post
    from accounting.tasks.master_opening import replay_access

    require_posting(current)
    if client is None:
        raise PostingDependencyError("Opening posting is unavailable; retry the same creation.")
    with tenant_scope(current.actor.tenant_id):
        async with factory() as db:
            await replay_access(db, current, identity)
            batch = await company_object(
                db, OpeningBatch, identity, company_id=current.context.company_id
            )
            if batch.journal_id is None:
                raise ConflictError("master opening journal is missing")
            journal_id = batch.journal_id
    # The original expected version and key stay fixed across prepare/commit and response loss.
    try:
        await post(
            factory,
            current,
            journal_id,
            ExpectedVersion(expected_version=1),
            "master-opening-" + identity.hex,
            client,
        )
    except PlatformError as exc:
        raise PostingDependencyError(
            "Creation is saved; opening posting is incomplete. Retry the same creation. "
            + exc.message
        ) from exc
    with tenant_scope(current.actor.tenant_id):
        async with factory() as db:
            batch = await company_object(
                db, OpeningBatch, identity, company_id=current.context.company_id
            )
            journal = await company_object(
                db, Journal, journal_id, company_id=current.context.company_id
            )
            if batch.status != "FINALIZED" or journal.status != "POSTED":
                raise ConflictError("master opening has not finished posting")
            posted_at, reservation_id = journal.posted_at, journal.reservation_id
            configuration_hash, features = journal.configuration_hash, set(journal.features)
    try:
        confirmed = await client.terminal(
            current.actor.tenant_id,
            current.context.company_id,
            operation_id=journal_id,
            outcome="confirmed",
            reference="accounting-journal:" + str(journal_id),
            posted_at=posted_at,
        )
    except ReservationError as exc:
        raise PostingDependencyError(
            "Opening posted; confirmation is pending. Retry the same creation."
        ) from exc
    if (
        confirmed.operation_id != journal_id
        or confirmed.reservation_id != reservation_id
        or confirmed.status != "confirmed"
        or confirmed.configuration_hash != configuration_hash
        or not features <= set(confirmed.features)
    ):
        raise PostingDependencyError(
            "Opening confirmation could not be verified. Retry the same creation."
        )
    # Acknowledge this exact durable terminal delivery, so period readiness does not
    # continue waiting for the background worker after the terminal was confirmed.
    # The infrastructure table is tenant-exempt: every owner predicate is explicit.
    with tenant_scope(current.actor.tenant_id):
        async with factory() as db, db.begin():
            delivery = await db.scalar(
                select(Outbox)
                .where(
                    Outbox.tenant_id == current.actor.tenant_id,
                    Outbox.aggregate_type == "accounting.journal",
                    Outbox.aggregate_id == journal_id,
                    Outbox.event_type == "accounting.company_posting.confirm",
                )
                .with_for_update()
            )
            if (
                delivery is None
                or delivery.payload.get("company_id") != str(current.context.company_id)
                or delivery.payload.get("operation_id") != str(journal_id)
            ):
                raise PostingDependencyError("Opening confirmation delivery could not be verified.")
            if delivery.published_at is None:
                delivery.published_at = utcnow()
                delivery.last_error = None
                delivery.attempt_count = min(delivery.attempt_count + 1, 32767)


async def record_outcome(
    db: AsyncSession, current: Access, batch: OpeningBatch, *, is_reversal: bool = False
) -> None:
    from accounting.tasks.financial_opening import audit

    row = await db.scalar(
        select(MasterOpeningBalance).where(
            MasterOpeningBalance.company_id == batch.company_id, MasterOpeningBalance.id == batch.id
        )
    )
    if row is None:
        return
    before = "POSTED" if is_reversal else "POSTING"
    if row.status != before:
        raise ConflictError("master opening is not awaiting this posting")
    row.status = "REVERSED" if is_reversal else "POSTED"
    row.row_version += 1
    row.updated_by = current.actor.user_id
    await db.flush()
    audit(db, current, row, "reverse" if is_reversal else "post", before={"status": before})
