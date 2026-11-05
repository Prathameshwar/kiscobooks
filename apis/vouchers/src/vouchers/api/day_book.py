"""Read-only activity query; no state, money or audit mutation."""

import uuid

from billing_platform.errors import ConflictError
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, session
from vouchers.models import core as m
from vouchers.schemas.day_book import DayBookPage, DayBookQuery, DayBookTypeRevisions
from vouchers.tasks.access import authorize, denied
from vouchers.tasks.common import get
from vouchers.tasks.day_book import query

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERRORS)


@router.get("/day-book/types/{type_id}/revisions", response_model=DayBookTypeRevisions)
async def type_revisions(
    type_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> DayBookTypeRevisions:
    from billing_platform.errors import PermissionDeniedError

    authorize(current, "read")
    if denied(
        current,
        "vouchers.configuration",
        {"id", "type_id", "revision_id", "type_revision_id", "revision_ids", "revision_number"},
        "read",
    ):
        raise PermissionDeniedError("voucher type revisions are not readable")
    await get(db, current, m.VoucherType, type_id)
    values = list(
        (
            await db.scalars(
                select(m.VoucherTypeRevision.id)
                .where(
                    m.VoucherTypeRevision.tenant_id == current.context.tenant_id,
                    m.VoucherTypeRevision.company_id == current.context.company_id,
                    m.VoucherTypeRevision.type_id == type_id,
                )
                .order_by(m.VoucherTypeRevision.revision_number)
                .limit(2001)
            )
        ).all()
    )
    if len(values) > 2000:
        raise ConflictError("this voucher type exceeds the Day Book revision filter limit")
    return DayBookTypeRevisions(type_id=type_id, revision_ids=values)


@router.post("/day-book/query", response_model=DayBookPage)
async def activity(
    body: DayBookQuery,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> DayBookPage:
    return await query(
        db,
        current,
        body,
        request.app.state.settings.artifact_signing_secret.get_secret_value().encode(),
    )
