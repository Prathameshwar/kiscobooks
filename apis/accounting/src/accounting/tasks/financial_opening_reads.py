"""Lean indexed opening evidence, explicit coverage and actor-bound private exports."""

import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.bulk_files import csv_document
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.listing import ListQuery, Page, SortColumn, fetch_page, resolve_sort
from billing_platform.pagination import CursorCodec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.models.financial_opening import FinancialOpeningEntry, FinancialOpeningRevision
from accounting.models.fiscal import FinancialSetup
from accounting.models.ledger import Journal
from accounting.models.masters import Account, AccountingSetup, Party
from accounting.models.subledger import OpeningBatch
from accounting.schemas.financial_opening import (
    FinancialOpeningExportTicket,
    FinancialOpeningPreview,
    FinancialOpeningReadiness,
    FinancialOpeningRevisionItem,
    OpeningDeclaration,
    OpeningEntryItem,
    OpeningEntryPostingLink,
    OpeningEntryQuery,
)
from accounting.tasks.access import authority_fingerprint
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.financial_opening import (
    audit,
    chunks,
    declaration,
    require_read,
    revision,
    validate,
)
from accounting.tasks.openings import opening_window_blockers


async def opening_state(
    db: AsyncSession, current: Any
) -> tuple[OpeningBatch | None, bool, list[str]]:
    """The company's current opening batch, whether pre-opening activity exists, and blockers."""
    company = current.context.company_id
    facts = financial_context(current)
    from accounting.tasks.master_opening_posting import company_batches

    batch = await db.scalar(
        select(OpeningBatch)
        .where(
            OpeningBatch.company_id == company,
            OpeningBatch.status.in_(["DRAFT", "FINALIZED"]),
            company_batches(),
        )
        .order_by(OpeningBatch.id.desc())
        .limit(1)
    )
    blockers = []
    if not await db.scalar(
        select(AccountingSetup.id).where(AccountingSetup.company_id == company).limit(1)
    ):
        blockers.append("ACCOUNTING_NOT_INITIALIZED")
    if not await db.scalar(
        select(FinancialSetup.id).where(FinancialSetup.company_id == company).limit(1)
    ):
        blockers.append("FINANCIAL_SETUP_NOT_INITIALIZED")
    blockers.extend(await opening_window_blockers(db, company, facts.books_begin_date))
    legacy = batch is None and bool(
        await db.scalar(
            select(Journal.id)
            .where(
                Journal.company_id == company,
                Journal.status.in_(["PREPARED", "POSTED"]),
                Journal.kind.not_in(["OPENING", "REVERSAL"]),
            )
            .limit(1)
        )
    )
    if legacy:
        blockers.append("LEGACY_ACTIVITY_REQUIRES_REVIEW")
    if batch:
        blockers.append(
            "OPENING_ALREADY_FINALIZED"
            if batch.status == "FINALIZED"
            else "RESUME_EXISTING_OPENING"
        )
    return batch, legacy, blockers


async def readiness(db: AsyncSession, current: Any) -> FinancialOpeningReadiness:
    require_read(current)
    company = current.context.company_id
    facts = financial_context(current)
    batch, legacy, blockers = await opening_state(db, current)
    target = ScopePath(company_id=company)
    return FinancialOpeningReadiness(
        company_id=company,
        books_begin_date=facts.books_begin_date,
        currency=current.context.base_currency,
        batch_id=batch.id if batch else None,
        status=batch.status if batch else "LEGACY_ACTIVITY" if legacy else "NOT_STARTED",
        blockers=blockers,
        can_prepare=not blockers
        and all(
            current.actor.allows_scope(key, target=target)
            for key in ("accounting.finance.manage", "period.post")
        ),
    )


async def preview(
    db: AsyncSession, current: Any, body: OpeningDeclaration
) -> FinancialOpeningPreview:
    plans = await validate(db, current, body)
    from accounting.domain.financial_opening import declaration_hash
    from accounting.domain.ledger import base_value

    facts = financial_context(current)
    total = sum(
        (
            entry.base_amount
            or base_value(
                entry.amount,
                entry.currency,
                entry.exchange_rate,
                body.currency,
                facts.amount_precision,
                facts.rounding_mode,
            )
            for entry in body.entries
            if entry.side == "DEBIT"
        ),
        Decimal(0),
    )
    return FinancialOpeningPreview(
        company_id=current.context.company_id,
        manifest_hash=declaration_hash(body),
        posting_date=body.posting_date,
        currency=body.currency,
        total_debit=str(total),
        total_credit=str(total),
        entry_count=len(body.entries),
        document_count=sum(len(entry.documents) for entry in body.entries),
        journal_count=len(plans),
        coverage_mode=body.coverage_mode,
        covered_through=body.covered_through,
    )


async def entries(
    db: AsyncSession, current: Any, identity: uuid.UUID, query: OpeningEntryQuery, secret: bytes
) -> Page[OpeningEntryItem]:
    require_read(current)
    if query.q:
        raise ValidationFailedError(
            "use typed account/party/source-key filters for opening entries"
        )
    batch = await company_object(db, OpeningBatch, identity, company_id=current.context.company_id)
    rev = await revision(db, current, batch)
    for key, model in (("account_id", Account), ("party_id", Party)):
        identity_filter = getattr(query, key)
        if identity_filter is not None:
            await company_object(db, model, identity_filter, company_id=batch.company_id)
    fields = tuple(OpeningEntryItem.model_fields)
    statement = select(*(getattr(FinancialOpeningEntry, key).label(key) for key in fields)).where(
        FinancialOpeningEntry.company_id == batch.company_id,
        FinancialOpeningEntry.revision_id == rev.id,
    )
    for key in ("account_id", "party_id", "role", "currency", "side", "source_key"):
        if (value := getattr(query, key)) is not None:
            statement = statement.where(getattr(FinancialOpeningEntry, key) == value)
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(FinancialOpeningEntry.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    context = canonical_json(
        {
            "resource": "financial-opening-entries",
            "company": str(batch.company_id),
            "tenant": str(current.actor.tenant_id),
            "revision": str(rev.id),
            "authority": authority_fingerprint(current),
            "query": query.model_dump(mode="json", exclude={"cursor"}),
        }
    ).decode()

    def project(row: Mapping[str, Any]) -> OpeningEntryItem:
        return OpeningEntryItem.model_validate(
            dict(row) | {"amount": str(row["amount"]), "base_amount": str(row["base_amount"])}
        )

    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=CursorCodec(secret, context=context),
        project=project,
    )


async def revisions(
    db: AsyncSession, current: Any, identity: uuid.UUID, query: ListQuery, secret: bytes
) -> Page[FinancialOpeningRevisionItem]:
    require_read(current)
    if query.q:
        raise ValidationFailedError("worksheet revisions do not support text search")
    await company_object(db, OpeningBatch, identity, company_id=current.context.company_id)
    statement = select(
        *(
            getattr(FinancialOpeningRevision, key).label(key)
            for key in FinancialOpeningRevisionItem.model_fields
        )
    ).where(
        FinancialOpeningRevision.company_id == current.context.company_id,
        FinancialOpeningRevision.batch_id == identity,
    )
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(FinancialOpeningRevision.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    context = canonical_json(
        {
            "resource": "financial-opening-revisions",
            "company": str(current.context.company_id),
            "tenant": str(current.actor.tenant_id),
            "batch": str(identity),
            "authority": authority_fingerprint(current),
            "query": query.model_dump(mode="json", exclude={"cursor"}),
        }
    ).decode()
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=CursorCodec(secret, context=context),
        project=lambda row: FinancialOpeningRevisionItem.model_validate(dict(row)),
    )


async def entry(
    db: AsyncSession, current: Any, identity: uuid.UUID, entry_id: uuid.UUID
) -> dict[str, Any]:
    require_read(current)
    batch = await company_object(db, OpeningBatch, identity, company_id=current.context.company_id)
    rev = await revision(db, current, batch)
    row = await company_object(db, FinancialOpeningEntry, entry_id, company_id=batch.company_id)
    if row.revision_id != rev.id:
        raise ValidationFailedError("entry is not part of the current declaration")
    return row.payload


async def posting_link(
    db: AsyncSession, current: Any, identity: uuid.UUID, entry_id: uuid.UUID
) -> OpeningEntryPostingLink:
    await entry(db, current, identity, entry_id)
    batch = await company_object(db, OpeningBatch, identity, company_id=current.context.company_id)
    record = await company_object(db, FinancialOpeningEntry, entry_id, company_id=batch.company_id)
    for chunk in await chunks(db, current, batch):
        keys = chunk.payload.get("entry_source_keys", [])
        if record.source_key in keys:
            journal = (
                await company_object(db, Journal, chunk.journal_id, company_id=batch.company_id)
                if chunk.journal_id
                else None
            )
            return OpeningEntryPostingLink(
                entry_id=record.id,
                source_key=record.source_key,
                chunk_id=chunk.id,
                journal_id=chunk.journal_id,
                line_sequence=keys.index(record.source_key) + 1,
                journal_status=journal.status if journal else "NOT_PREPARED",
            )
    raise ConflictError("opening execution lineage is incomplete")


async def export_codec(
    db: AsyncSession, current: Any, identity: uuid.UUID, secret: bytes
) -> tuple[OpeningBatch, CursorCodec]:
    require_read(current)
    current.actor.require_scope(
        "accounting.export.read", target=ScopePath(company_id=current.context.company_id)
    )
    batch = await company_object(db, OpeningBatch, identity, company_id=current.context.company_id)
    rev = await revision(db, current, batch)
    context = canonical_json(
        {
            "resource": "financial-opening-export",
            "tenant": str(current.actor.tenant_id),
            "company": str(batch.company_id),
            "actor": str(current.actor.user_id),
            "revision": str(rev.id),
            "version": batch.row_version,
            "authority": authority_fingerprint(current),
        }
    ).decode()
    return batch, CursorCodec(secret, ttl_seconds=300, context=context)


async def ticket(
    db: AsyncSession, current: Any, identity: uuid.UUID, secret: bytes
) -> FinancialOpeningExportTicket:
    _, codec = await export_codec(db, current, identity, secret)
    token = codec.encode({"id": str(identity)})
    return FinancialOpeningExportTicket(
        token=token,
        download_path=f"/v1/companies/{current.context.company_id}/opening-batches/workspaces/{identity}/export?token={token}",
    )


async def export(
    db: AsyncSession, current: Any, identity: uuid.UUID, token: str, secret: bytes
) -> bytes:
    batch, codec = await export_codec(db, current, identity, secret)
    if codec.decode(token) != {"id": str(identity)}:
        raise ValidationFailedError("invalid opening export ticket")
    body = await declaration(db, current, batch)
    rows = [
        [
            entry.source_key,
            str(entry.account_id),
            entry.side,
            entry.currency,
            str(entry.amount),
            str(entry.base_amount) if entry.base_amount else "",
            str(entry.exchange_rate),
            str(len(entry.documents)),
            body.posting_date.isoformat(),
            body.covered_through.isoformat(),
            body.coverage_mode,
        ]
        for entry in body.entries
    ]
    audit(db, current, batch, "export")
    return csv_document(
        [
            "source_key",
            "account_id",
            "side",
            "currency",
            "amount",
            "explicit_base_amount",
            "exchange_rate",
            "document_count",
            "opening_date",
            "covered_through",
            "coverage_mode",
        ],
        rows,
    )
