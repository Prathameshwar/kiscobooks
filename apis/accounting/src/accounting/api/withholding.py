"""Read-only TDS/TCS withholding preview."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import ERROR_RESPONSES, no_query, session
from accounting.schemas.withholding import WithholdingPreview, WithholdingPreviewRequest
from accounting.tasks import withholding

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERROR_RESPONSES)


async def preview_permission(current: Access = Depends(access)) -> None:
    # A route dependency resolves before the body, so unpermitted callers get 403, not 422.
    withholding.require_preview_permission(current)


@router.post(
    "/withholding-previews",
    response_model=WithholdingPreview,
    dependencies=[Depends(preview_permission)],
)
async def preview(
    company_id: uuid.UUID,
    body: WithholdingPreviewRequest,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> WithholdingPreview:
    no_query(request)
    return await withholding.preview(db, current, body)
