"""Read-only correction preflight and durable reversal lineage for native opening journals."""

import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.models.ledger import Journal
from accounting.models.masters import AccountingSetup
from accounting.models.subledger import OpeningBatch
from accounting.schemas.financial_opening import OpeningJournalRecovery
from accounting.tasks.finance_records import require_fields
from accounting.tasks.financial_opening import chunks, require_read
from accounting.tasks.openings import opening_window_blockers
from accounting.tasks.stock_opening_control import pending
from accounting.tasks.subledger_posting import validate_reversal


async def recovery(
    db: AsyncSession, current: Any, batch_id: uuid.UUID, journal_id: uuid.UUID
) -> OpeningJournalRecovery:
    require_read(current)
    target = ScopePath(company_id=current.context.company_id)
    current.actor.require_scope("ledger.read", target=target)
    require_fields(current, "journal", {"id", "status", "row_version", "reversal_of_id"})
    # The same shared company fence as reconciliation prevents mixed correction facts.
    await db.scalar(
        select(AccountingSetup.id)
        .where(AccountingSetup.company_id == current.context.company_id)
        .with_for_update(read=True)
    )
    batch = await company_object(db, OpeningBatch, batch_id, company_id=current.context.company_id)
    journal = await company_object(db, Journal, journal_id, company_id=current.context.company_id)
    links = await chunks(db, current, batch)
    if journal.id not in {link.journal_id for link in links}:
        raise ConflictError("journal does not belong to this opening declaration")
    reverse = await db.scalar(
        select(Journal)
        .where(
            Journal.company_id == batch.company_id,
            Journal.reversal_of_id == journal.id,
            Journal.status != "VOID",
        )
        .limit(1)
    )
    can_cancel = all(
        current.actor.allows_scope(key, target=target)
        for key in ("accounting.finance.manage", "ledger.post_journal")
    )
    allowed = all(
        current.actor.allows_scope(key, target=target)
        for key in ("accounting.finance.manage", "ledger.post_journal", "period.post")
    )
    blockers = await opening_window_blockers(db, batch.company_id, batch.posting_date)
    if not allowed:
        blockers.append("POSTING_AUTHORITY_REQUIRED")
    if journal.status != "POSTED":
        blockers.append("ORIGINAL_JOURNAL_NOT_POSTED")
    if reverse:
        blockers.append("REVERSAL_ALREADY_EXISTS")
    if await pending(db, batch.company_id):
        blockers.append("NATIVE_CONFIRMATION_PENDING")
    if not blockers:
        try:
            await validate_reversal(db, current, journal)
        except (ConflictError, PermissionDeniedError) as problem:
            blockers.append(problem.message)
    return OpeningJournalRecovery(
        company_id=batch.company_id,
        batch_id=batch.id,
        journal_id=journal.id,
        journal_status=journal.status,
        expected_version=journal.row_version,
        can_cancel=can_cancel and journal.status in {"DRAFT", "PREPARED"},
        can_reverse=not blockers,
        reversal_blockers=blockers,
        reversal_journal_id=reverse.id if reverse else None,
        reversal_status=reverse.status if reverse else None,
        reversal_expected_version=reverse.row_version if reverse else None,
        can_cancel_reversal=can_cancel
        and reverse is not None
        and reverse.status in {"DRAFT", "PREPARED"},
    )
