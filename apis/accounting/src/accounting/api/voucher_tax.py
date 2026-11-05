"""Read-only voucher Tax Analysis preview and the stored journal tax evidence."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import ERROR_RESPONSES, no_query, session
from accounting.api.fiscal import financial_rate
from accounting.api.subledger import add_reads
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.schemas.subledger import TaxPreviewRequest
from accounting.schemas.voucher_tax import JournalTaxListItem, TaxPreview
from accounting.tasks import voucher_tax
from accounting.tasks.access import authorize

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERROR_RESPONSES)


async def preview_permission(current: Access = Depends(access)) -> None:
    # A route dependency resolves before the body, so unpermitted callers get 403, not 422.
    authorize(current, FINANCIAL_BY_NAME["journal_tax"], "read")


@router.post(
    "/voucher-tax-previews",
    response_model=TaxPreview,
    dependencies=[Depends(preview_permission), Depends(financial_rate)],
)
async def preview(
    company_id: uuid.UUID,
    body: TaxPreviewRequest,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> TaxPreview:
    no_query(request)
    return await voucher_tax.preview(db, current, body)


add_reads(FINANCIAL_BY_NAME["journal_tax"], JournalTaxListItem, target=router)
