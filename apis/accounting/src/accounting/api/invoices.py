"""Posted invoice facts with sparse fields and company-bound keyset cursors."""

import uuid
from typing import Annotated, Any, Literal

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.pagination import CursorCodec
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import ERROR_RESPONSES, session, unique_query
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.invoice import InvoiceRecord
from accounting.models.ledger import Journal
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.schemas.invoice import (
    InvoiceAllocationFactDetail,
    InvoiceComponentFactDetail,
    InvoiceFactListItem,
    InvoiceFactPage,
    InvoiceHistoryQuery,
    InvoicePostingLineDetail,
    InvoiceRecordDetail,
    InvoiceRecordListItem,
    InvoiceRecordPage,
    InvoiceRecordQuery,
    InvoiceSupplyFactDetail,
    InvoiceTaxComponentDetail,
)
from accounting.tasks.access import authority_fingerprint, authorize, readable
from accounting.tasks.commands import protected
from accounting.tasks.finance_records import require_fields

Section = Literal["supplies", "components", "allocations", "tax-components", "posting-lines"]
SECTIONS = {
    "supplies": "invoice_supply_fact",
    "components": "invoice_component_fact",
    "allocations": "invoice_allocation_fact",
    "tax-components": "invoice_tax_component",
    "posting-lines": "invoice_posting_line",
}
router = APIRouter(
    prefix="/v1/companies/{company_id}/invoice-records",
    responses=ERROR_RESPONSES,
    dependencies=[Depends(unique_query)],
)


def codec(request: Request, current: Access, context: str) -> CursorCodec:
    return CursorCodec(
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        context=f"invoices:{current.actor.tenant_id}:{current.context.company_id}:{authority_fingerprint(current)}:{context}",
    )


def after(cursor: str | None, signing: CursorCodec) -> uuid.UUID | None:
    if cursor is None:
        return None
    try:
        return uuid.UUID(signing.decode(cursor)["id"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValidationFailedError("invalid invoice cursor") from error


def page(rows: list[dict[str, Any]], limit: int, signing: CursorCodec) -> dict[str, Any]:
    return {
        "items": rows[:limit],
        "page": {
            "limit": limit,
            "has_more": len(rows) > limit,
            "next_cursor": signing.encode({"id": str(rows[limit - 1]["id"])})
            if len(rows) > limit
            else None,
        },
    }


async def posted(db: AsyncSession, current: Access, identity: uuid.UUID) -> InvoiceRecord:
    spec = FINANCIAL_BY_NAME["invoice_record"]
    authorize(current, spec, "read")
    row = await company_object(db, InvoiceRecord, identity, company_id=current.context.company_id)
    require_fields(current, "invoice_record", {"intent_id"}, row=row)
    intent = await company_object(db, VoucherMoneyIntent, row.intent_id, company_id=row.company_id)
    if intent.journal_id is None:
        raise ConflictError("invoice has not been posted")
    journal = await company_object(db, Journal, intent.journal_id, company_id=row.company_id)
    require_fields(current, "journal", {"status"}, row=journal)
    if journal.status != "POSTED":
        raise ConflictError("invoice has not been posted")
    return row


@router.get("", response_model=InvoiceRecordPage, response_model_exclude_none=True)
async def records(
    company_id: uuid.UUID,
    request: Request,
    response: Response,
    filters: Annotated[InvoiceRecordQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    spec = FINANCIAL_BY_NAME["invoice_record"]
    authorize(current, spec, "read")
    allowed = readable(current, spec)
    require_fields(current, "invoice_record", {"intent_id"})
    require_fields(current, "journal", {"status"})
    if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
        raise ValidationFailedError("invalid invoice posting-date range")
    for name, active in {
        "kind": filters.kind,
        "party_account_id": filters.party_account_id,
        "posting_date": filters.date_from or filters.date_to,
    }.items():
        if active and name not in allowed:
            raise PermissionDeniedError("invoice filter field is not readable")
    signing = codec(request, current, filters.model_dump_json(exclude={"cursor"}))
    columns = sorted(set(InvoiceRecordListItem.model_fields) & allowed)
    query = (
        select(*(getattr(InvoiceRecord, name) for name in columns))
        .join(
            VoucherMoneyIntent,
            (VoucherMoneyIntent.id == InvoiceRecord.intent_id)
            & (VoucherMoneyIntent.company_id == InvoiceRecord.company_id),
        )
        .join(
            Journal,
            (Journal.id == VoucherMoneyIntent.journal_id)
            & (Journal.company_id == InvoiceRecord.company_id),
        )
        .where(InvoiceRecord.company_id == company_id, Journal.status == "POSTED")
    )
    if filters.kind:
        query = query.where(InvoiceRecord.kind == filters.kind)
    if filters.party_account_id:
        from accounting.models.masters import Account

        await company_object(db, Account, filters.party_account_id, company_id=company_id)
        query = query.where(InvoiceRecord.party_account_id == filters.party_account_id)
    if filters.date_from:
        query = query.where(InvoiceRecord.posting_date >= filters.date_from)
    if filters.date_to:
        query = query.where(InvoiceRecord.posting_date <= filters.date_to)
    if identity := after(filters.cursor, signing):
        query = query.where(InvoiceRecord.id > identity)
    rows = (await db.execute(query.order_by(InvoiceRecord.id).limit(filters.limit + 1))).mappings()
    return page([dict(row) for row in rows], filters.limit, signing)


@router.get("/{invoice_id}", response_model=InvoiceRecordDetail, response_model_exclude_none=True)
async def record(
    company_id: uuid.UUID,
    invoice_id: uuid.UUID,
    response: Response,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    response.headers["Cache-Control"] = "no-store"
    row = await posted(db, current, invoice_id)
    return protected(row, FINANCIAL_BY_NAME["invoice_record"], current)


@router.get(
    "/{invoice_id}/{section}", response_model=InvoiceFactPage, response_model_exclude_none=True
)
async def facts(
    company_id: uuid.UUID,
    invoice_id: uuid.UUID,
    section: Section,
    request: Request,
    response: Response,
    filters: Annotated[InvoiceHistoryQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    await posted(db, current, invoice_id)
    spec = FINANCIAL_BY_NAME[SECTIONS[section]]
    authorize(current, spec, "read")
    require_fields(current, spec.name, {"invoice_id"})
    names = sorted(set(InvoiceFactListItem.model_fields) & readable(current, spec))
    signing = codec(request, current, f"{invoice_id}:{section}:{filters.limit}")
    model: Any = spec.model
    query = select(*(getattr(model, name) for name in names)).where(
        model.company_id == company_id, model.invoice_id == invoice_id
    )
    if identity := after(filters.cursor, signing):
        query = query.where(model.id > identity)
    rows = (await db.execute(query.order_by(model.id).limit(filters.limit + 1))).mappings()
    return page([dict(row) for row in rows], filters.limit, signing)


@router.get(
    "/{invoice_id}/{section}/{object_id}",
    response_model=InvoiceSupplyFactDetail
    | InvoiceComponentFactDetail
    | InvoiceAllocationFactDetail
    | InvoiceTaxComponentDetail
    | InvoicePostingLineDetail,
    response_model_exclude_none=True,
)
async def fact(
    company_id: uuid.UUID,
    invoice_id: uuid.UUID,
    section: Section,
    object_id: uuid.UUID,
    response: Response,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    response.headers["Cache-Control"] = "no-store"
    await posted(db, current, invoice_id)
    spec = FINANCIAL_BY_NAME[SECTIONS[section]]
    authorize(current, spec, "read")
    row: Any = await company_object(db, spec.model, object_id, company_id=company_id)
    require_fields(current, spec.name, {"invoice_id"}, row=row)
    if row.invoice_id != invoice_id:
        raise PermissionDeniedError("invoice fact is outside the requested invoice")
    return protected(row, spec, current)
