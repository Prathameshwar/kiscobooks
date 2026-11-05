"""Scoped private company documents and bounded pending-upload reconciliation."""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor
from identity.api.children import contact_company
from identity.api.dependencies import session
from identity.api.lifecycle import ToggleRequest
from identity.api.listing import paged
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import CompanyDocument
from identity.schemas.base import Page
from identity.schemas.documents import DocumentItem, DocumentLink, DocumentWrite, ReconcileResult
from identity.services.audit import record
from identity.services.documents import storage

router = APIRouter(
    prefix="/v1/companies/{company_id}/documents",
    route_class=StrictRoute,
    responses=ERROR_RESPONSES,
)


def audit(db: AsyncSession, current: Actor, row: CompanyDocument, action: str) -> None:
    record(
        db,
        current,
        action="company.document_" + action,
        entity="company_document",
        entity_id=row.id,
        company_id=row.company_id,
    )


async def document(
    db: AsyncSession, company_id: uuid.UUID, document_id: uuid.UUID
) -> CompanyDocument:
    row = await db.get(CompanyDocument, document_id)
    if row is None or row.company_id != company_id:
        raise NotFoundError("document not found")
    return row


@router.put("/{document_id}/upload", response_model=DocumentLink)
async def upload(
    company_id: uuid.UUID,
    document_id: uuid.UUID,
    body: DocumentWrite,
    request: Request,
    response: Response,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> DocumentLink:
    await contact_company(db, current, company_id, True)
    if document_id.int == 0:
        raise ValidationFailedError("document identifier must be nonzero")
    provider = storage(request)
    row = await db.get(CompanyDocument, document_id)
    if row is not None:
        if row.company_id != company_id:
            raise NotFoundError("document not found")
        if row.storage_state != "pending" or any(
            getattr(row, key) != value for key, value in body.model_dump().items()
        ):
            raise ConflictError("document identifier already has a different upload")
    else:
        pending = await db.scalars(
            select(CompanyDocument.id)
            .where(
                CompanyDocument.company_id == company_id, CompanyDocument.storage_state == "pending"
            )
            .limit(20)
        )
        if len(list(pending)) >= 20:
            raise ConflictError("finish or reconcile pending document uploads first")
        row = CompanyDocument(
            id=document_id,
            tenant_id=current.tenant_id,
            company_id=company_id,
            **body.model_dump(),
            file_url=f"identity/{current.tenant_id}/{company_id}/{document_id}",
            storage_state="pending",
            is_active=True,
            created_by=current.user_id,
            upload_expires_at=utcnow() + dt.timedelta(minutes=5),
        )
        db.add(row)
        audit(db, current, row, "upload_requested")
    result = await provider.link(row, upload=True)
    response.headers["Cache-Control"] = "no-store"
    await db.flush()
    return result


@router.post("/{document_id}/finalize", response_model=DocumentItem)
async def finalize(
    company_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyDocument:
    await contact_company(db, current, company_id, True)
    row = await document(db, company_id, document_id)
    if row.storage_state == "ready":
        return row
    if (
        row.storage_state != "pending"
        or row.upload_expires_at is None
        or row.upload_expires_at <= utcnow()
    ):
        raise ConflictError("upload is not pending or has expired")
    row.blob_snapshot = await storage(request).finalize(row)
    row.storage_state, row.finalized_at, row.updated_by = "ready", utcnow(), current.user_id
    audit(db, current, row, "finalized")
    await db.flush()
    return row


@router.post("/{document_id}/download", response_model=DocumentLink)
async def download(
    company_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    response: Response,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> DocumentLink:
    await contact_company(db, current, company_id, False)
    row = await document(db, company_id, document_id)
    if row.storage_state != "ready" or not row.is_active:
        raise ConflictError("document is not available for download")
    result = await storage(request).link(row, upload=False)
    audit(db, current, row, "downloaded")
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("", response_model=Page[DocumentItem])
async def documents(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[DocumentItem]:
    await contact_company(db, current, company_id, False)
    return await paged(
        db,
        request,
        select(CompanyDocument).where(CompanyDocument.company_id == company_id),
        model=CompanyDocument,
        schema=DocumentItem,
        limit=limit,
        cursor=cursor,
    )


@router.post("/{document_id}/lifecycle", response_model=DocumentItem)
async def lifecycle(
    company_id: uuid.UUID,
    document_id: uuid.UUID,
    body: ToggleRequest,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyDocument:
    await contact_company(db, current, company_id, True)
    row = await document(db, company_id, document_id)
    if row.storage_state != "ready":
        raise ConflictError("only finalized documents have an active lifecycle")
    if row.is_active != body.is_active:
        row.is_active, row.updated_by = body.is_active, current.user_id
        row.deactivated_at = None if body.is_active else utcnow()
        row.deactivated_by = None if body.is_active else current.user_id
        audit(db, current, row, "lifecycle_changed")
    await db.flush()
    return row


@router.post("/reconcile", response_model=ReconcileResult)
async def reconcile(
    company_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ReconcileResult:
    # Cleanup remains possible for inactive companies; the tenant lock excludes finalize races.
    current.require_scope("company.update", target=ScopePath(company_id=company_id))
    rows = list(
        await db.scalars(
            select(CompanyDocument)
            .where(
                CompanyDocument.company_id == company_id,
                CompanyDocument.storage_state == "pending",
                CompanyDocument.upload_expires_at < utcnow() - dt.timedelta(minutes=1),
            )
            .order_by(CompanyDocument.id)
            .limit(5)
        )
    )
    for row in rows:
        await storage(request).delete_pending(row)
        row.storage_state, row.is_active = "expired", False
        row.deactivated_at, row.deactivated_by = utcnow(), current.user_id
        row.updated_by = current.user_id
        audit(db, current, row, "upload_expired")
    await db.flush()
    return ReconcileResult(expired=len(rows))
