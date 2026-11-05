"""Bounded opening evidence; derived values obey contributing field policies."""

import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.listing import ListQuery, Page, SortColumn, fetch_page, resolve_sort
from billing_platform.pagination import CursorCodec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from accounting.api.auth import Access
from accounting.models.stock import (
    StockMovement,
    StockPosition,
    StockPosting,
    StockReceiptOrigin,
    StockValueEntry,
)
from accounting.models.stock_opening import (
    StockOpeningClaim,
    StockOpeningControl,
    StockOpeningRevision,
)
from accounting.schemas.stock_opening import (
    OpeningAccountingPreview,
    OpeningCohort,
    OpeningCohortQuery,
    OpeningManifest,
    OpeningProjectedClaim,
    OpeningProjectedEntry,
    OpeningRevisionItem,
)
from accounting.stock_resources import STOCK_MOVEMENT, STOCK_POLICY
from accounting.tasks.access import authority_fingerprint
from accounting.tasks.stock_opening_control import require_capture_read
from accounting.tasks.stock_reads import view


async def accounting_preview(
    db: AsyncSession, current: Access, identity: uuid.UUID
) -> OpeningAccountingPreview:
    from accounting.tasks.stock_opening_control import active_claims
    from accounting.tasks.stock_policy import effective

    require_capture_read(current)
    if (
        not {"inventory_account_id", "opening_offset_account_id", "valid_from", "valid_to"}
        <= view(current, STOCK_POLICY)[2]
    ):
        raise PermissionDeniedError("opening account mapping must be readable")
    row = await company_object(
        db, StockOpeningControl, identity, company_id=current.context.company_id, lock=True
    )
    manifest = OpeningManifest.model_validate(row.manifest)
    policy = await effective(db, current, row.books_begin_date)
    applied = {claim.source_key for claim in await active_claims(db, row)}
    remaining = [
        line for line in manifest.lines if line.opening and line.opening.source_key not in applied
    ]
    total = sum((line.received_value or Decimal(0) for line in remaining), Decimal(0))
    claims: dict[uuid.UUID, Decimal] = {}
    if manifest.opening_mode == "LINKED_GL":
        for line in remaining:
            if line.opening_journal_line_id:
                claims[line.opening_journal_line_id] = claims.get(
                    line.opening_journal_line_id, Decimal(0)
                ) + (line.received_value or Decimal(0))
    return OpeningAccountingPreview(
        company_id=row.company_id,
        control_id=row.id,
        expected_version=row.row_version,
        manifest_hash=row.manifest_hash,
        currency=row.currency,
        opening_mode=manifest.opening_mode,
        remaining_value=total,
        additional_gl_value=total if manifest.opening_mode == "COMBINED" else Decimal(0),
        entries=[
            OpeningProjectedEntry(
                account_id=policy.inventory_account_id, side="DEBIT", amount=total
            ),
            OpeningProjectedEntry(
                account_id=policy.opening_offset_account_id, side="CREDIT", amount=total
            ),
        ]
        if manifest.opening_mode == "COMBINED" and total
        else [],
        linked_claims=[
            OpeningProjectedClaim(journal_line_id=key, amount=value)
            for key, value in sorted(claims.items())
        ],
    )


async def revisions(
    db: AsyncSession, current: Access, identity: uuid.UUID, query: ListQuery, secret: bytes
) -> Page[OpeningRevisionItem]:
    require_capture_read(current)
    await company_object(db, StockOpeningControl, identity, company_id=current.context.company_id)
    if query.q:
        raise ValidationFailedError("opening revisions do not support text search")
    statement = select(
        *(getattr(StockOpeningRevision, key) for key in OpeningRevisionItem.model_fields)
    ).where(
        StockOpeningRevision.company_id == current.context.company_id,
        StockOpeningRevision.control_id == identity,
    )
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(StockOpeningRevision.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    context = canonical_json(
        {
            "resource": "opening-revisions",
            "tenant": str(current.actor.tenant_id),
            "company": str(current.context.company_id),
            "control": str(identity),
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
        project=OpeningRevisionItem.model_validate,
    )


async def cohorts(
    db: AsyncSession, current: Access, identity: uuid.UUID, query: OpeningCohortQuery, secret: bytes
) -> Page[OpeningCohort]:
    require_capture_read(current)
    if "stock_date" not in view(current, STOCK_MOVEMENT)[2]:
        raise PermissionDeniedError("opening history inputs must be readable")
    await company_object(db, StockOpeningControl, identity, company_id=current.context.company_id)
    if query.q:
        raise ValidationFailedError("opening cohorts use typed product/warehouse filters")
    reversed_posting = aliased(StockPosting)
    statement = select(
        StockOpeningClaim.id,
        StockOpeningClaim.source_key,
        StockOpeningClaim.posting_id,
        StockPosition.item_id,
        StockPosition.warehouse_id,
        StockPosition.bin_id,
        StockPosition.lot_id,
        StockMovement.quantity,
        StockValueEntry.amount.label("value"),
        StockOpeningClaim.currency,
        StockPosting.stock_date.label("cutover_date"),
        StockReceiptOrigin.received_on,
        StockReceiptOrigin.history_known,
        reversed_posting.id.label("reversal_id"),
    )
    statement = statement.select_from(StockOpeningClaim).join(
        StockPosting, StockPosting.id == StockOpeningClaim.posting_id
    )
    statement = statement.join(StockMovement, StockMovement.id == StockOpeningClaim.movement_id)
    statement = statement.join(StockPosition, StockPosition.id == StockMovement.position_id)
    statement = statement.join(StockValueEntry, StockValueEntry.movement_id == StockMovement.id)
    statement = statement.join(
        StockReceiptOrigin, StockReceiptOrigin.movement_id == StockMovement.id
    )
    statement = statement.outerjoin(
        reversed_posting,
        (reversed_posting.company_id == current.context.company_id)
        & (reversed_posting.reverses_id == StockPosting.id),
    )
    statement = statement.where(
        StockOpeningClaim.company_id == current.context.company_id,
        StockOpeningClaim.control_id == identity,
        StockPosting.company_id == current.context.company_id,
        StockMovement.company_id == current.context.company_id,
        StockPosition.company_id == current.context.company_id,
        StockValueEntry.company_id == current.context.company_id,
        StockReceiptOrigin.company_id == current.context.company_id,
    )
    if not query.include_reversed:
        statement = statement.where(reversed_posting.id.is_(None))
    if query.item_id:
        statement = statement.where(StockPosition.item_id == query.item_id)
    if query.warehouse_id:
        statement = statement.where(StockPosition.warehouse_id == query.warehouse_id)
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(StockOpeningClaim.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    context = canonical_json(
        {
            "resource": "opening-cohorts",
            "tenant": str(current.actor.tenant_id),
            "company": str(current.context.company_id),
            "control": str(identity),
            "authority": authority_fingerprint(current),
            "query": query.model_dump(mode="json", exclude={"cursor"}),
        }
    ).decode()

    def project(row: Mapping[str, Any]) -> OpeningCohort:
        data = dict(row)
        data["history_known"] = data["history_known"] is True
        if not data["history_known"]:
            data["received_on"] = None
        data["reversed"] = data.pop("reversal_id") is not None
        return OpeningCohort.model_validate(data)

    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=CursorCodec(secret, context=context),
        project=project,
    )
