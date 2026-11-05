"""Native purchase-tax actions using the existing journal posting authority."""

import uuid
from typing import Any

from billing_platform.db.access import company_object
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import (
    ERROR_RESPONSES,
    Idempotency,
    no_query,
    response,
    session,
    unique_query,
)
from accounting.api.fiscal import financial_rate
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.invoice_credit import InvoiceCreditAction
from accounting.schemas.invoice_credit import (
    CreditActionRequest,
    InvoiceCreditActionDetail,
    InvoiceCreditPosition,
)
from accounting.tasks import invoice_credit
from accounting.tasks.access import authorize
from accounting.tasks.commands import protected

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses=ERROR_RESPONSES,
    dependencies=[Depends(unique_query)],
)


@router.post(
    "/invoice-credit-actions",
    response_model=InvoiceCreditActionDetail,
    status_code=201,
    dependencies=[Depends(financial_rate)],
)
async def create(
    company_id: uuid.UUID,
    body: CreditActionRequest,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await invoice_credit.create(
            request.app.state.session_factory, current, body, idempotency_key
        ),
    )


@router.get("/invoice-credit-actions/{object_id}", response_model=InvoiceCreditActionDetail)
async def get(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    spec = FINANCIAL_BY_NAME["invoice_credit_action"]
    authorize(current, spec, "read")
    row = await company_object(db, InvoiceCreditAction, object_id, company_id=company_id)
    return protected(row, spec, current)


@router.get(
    "/invoice-tax-components/{object_id}/credit-position", response_model=InvoiceCreditPosition
)
async def position(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> InvoiceCreditPosition:
    authorize(current, FINANCIAL_BY_NAME["invoice_tax_component"], "read")
    return await invoice_credit.read_position(db, current, object_id)
