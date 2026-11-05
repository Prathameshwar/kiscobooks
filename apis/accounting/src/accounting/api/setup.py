"""Company setup actions."""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import ERROR_RESPONSES, Idempotency, no_query, response, session
from accounting.schemas.masters import AccountingSetupDetail, Input
from accounting.schemas.setup import TemplatePreview, TemplateResult, TemplateSelection
from accounting.tasks.commands import initialize
from accounting.tasks.templates import install, preview

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERROR_RESPONSES)


@router.post("/accounting-setup/preview", response_model=TemplatePreview)
async def preview_template(
    company_id: uuid.UUID,
    body: TemplateSelection,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> TemplatePreview:
    no_query(request)
    return await preview(db, current, body)


@router.post("/accounting-setup/install", response_model=TemplateResult)
async def install_template(
    company_id: uuid.UUID,
    body: TemplateSelection,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request, await install(request.app.state.session_factory, current, body, idempotency_key)
    )


@router.post("/accounting-setup/initialize", response_model=AccountingSetupDetail)
async def initialize_company(
    company_id: uuid.UUID,
    body: Input,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request, await initialize(request.app.state.session_factory, current, idempotency_key)
    )
