import uuid

from billing_platform.db.access import company_object
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import ERROR_RESPONSES, Idempotency, no_query, response, session
from accounting.models.workflows import MappingDraft
from accounting.resources import BY_NAME
from accounting.schemas.masters import ExpectedVersion
from accounting.schemas.workflows import MappingDraftCreate, MappingDraftDetail, MappingDraftUpdate
from accounting.tasks.access import authorize
from accounting.tasks.mapping_drafts import command, detail, validate_draft

router = APIRouter(
    prefix="/v1/companies/{company_id}/posting-mapping-drafts", responses=ERROR_RESPONSES
)


@router.post("", response_model=MappingDraftDetail, status_code=201)
async def create(
    company_id: uuid.UUID,
    body: MappingDraftCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await command(
            request.app.state.session_factory,
            current,
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.get("/{object_id}", response_model=MappingDraftDetail)
async def read(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> MappingDraftDetail:
    no_query(request)
    authorize(current, BY_NAME["account_posting_mapping"], "read")
    return detail(await company_object(db, MappingDraft, object_id, company_id=company_id), current)


@router.patch("/{object_id}", response_model=MappingDraftDetail)
async def update(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: MappingDraftUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await command(
            request.app.state.session_factory,
            current,
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post("/{object_id}/validate", response_model=MappingDraftDetail)
async def validate(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> MappingDraftDetail:
    no_query(request)
    return await validate_draft(db, current, object_id)


@router.post("/{object_id}/publish", response_model=MappingDraftDetail)
async def publish(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await command(
            request.app.state.session_factory,
            current,
            "publish",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )
