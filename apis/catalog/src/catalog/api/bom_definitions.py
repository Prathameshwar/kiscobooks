"""Native BOM drafts, immutable publications and non-posting preview routes."""

import uuid
from typing import Annotated, Literal

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, command_response, no_query, unique_query
from catalog.models.boms import BomComponent, BomDraft, BomOutput, BomRevision
from catalog.schemas.boms import (
    BomDraftDetail,
    BomDraftInput,
    BomDraftListItem,
    BomDraftUpdate,
    BomHistoryQuery,
    BomLineQuery,
    BomRevisionDetail,
    BomRevisionListItem,
    ComponentListItem,
    OutputListItem,
    PreviewDetail,
    PreviewInput,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks import bom_reads, boms

router = APIRouter(
    prefix="/v1/companies/{company_id}/boms/{bom_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


async def write(
    request: Request,
    current: Actor,
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    body: BomDraftInput | BomDraftUpdate | ExpectedVersion,
    key: str,
    action: Literal["create", "update", "publish", "retire"],
    object_id: uuid.UUID | None = None,
) -> JSONResponse:
    no_query(request)
    result = await boms.command(
        request.app.state.session_factory, current, company_id, bom_id, body, key, action, object_id
    )
    return command_response(request, result, created=action == "create")


@router.get(
    "/drafts",
    response_model=Page[BomDraftListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_bom_draft",
    dependencies=[Depends(unique_query)],
)
async def list_bom_draft(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    query: Annotated[BomHistoryQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await bom_reads.list_rows(
        db,
        current,
        company_id,
        bom_id,
        BomDraft,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/drafts/{object_id}",
    response_model=BomDraftDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_bom_draft",
    dependencies=[Depends(no_query)],
)
async def get_bom_draft(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    return await boms.read_definition(db, current, company_id, bom_id, object_id, BomDraft)


@router.post(
    "/drafts/{object_id}/preview",
    response_model=PreviewDetail,
    operation_id="preview_catalog_bom_draft",
    dependencies=[Depends(no_query)],
)
async def preview_bom_draft(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    body: PreviewInput,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> PreviewDetail:
    return await bom_reads.preview_definition(
        db, current, company_id, bom_id, object_id, BomDraft, body
    )


@router.get(
    "/drafts/{object_id}/components",
    response_model=Page[ComponentListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_bom_draft_components",
    dependencies=[Depends(unique_query)],
)
async def list_bom_draft_components(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[BomLineQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await bom_reads.list_children(
        db,
        current,
        company_id,
        bom_id,
        object_id,
        BomDraft,
        BomComponent,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/drafts/{object_id}/outputs",
    response_model=Page[OutputListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_bom_draft_outputs",
    dependencies=[Depends(unique_query)],
)
async def list_bom_draft_outputs(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[BomLineQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await bom_reads.list_children(
        db,
        current,
        company_id,
        bom_id,
        object_id,
        BomDraft,
        BomOutput,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/revisions",
    response_model=Page[BomRevisionListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_bom_revision",
    dependencies=[Depends(unique_query)],
)
async def list_bom_revision(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    query: Annotated[BomHistoryQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await bom_reads.list_rows(
        db,
        current,
        company_id,
        bom_id,
        BomRevision,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/revisions/{object_id}",
    response_model=BomRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_bom_revision",
    dependencies=[Depends(no_query)],
)
async def get_bom_revision(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    return await boms.read_definition(db, current, company_id, bom_id, object_id, BomRevision)


@router.post(
    "/revisions/{object_id}/preview",
    response_model=PreviewDetail,
    operation_id="preview_catalog_bom_revision",
    dependencies=[Depends(no_query)],
)
async def preview_bom_revision(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    body: PreviewInput,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> PreviewDetail:
    return await bom_reads.preview_definition(
        db, current, company_id, bom_id, object_id, BomRevision, body
    )


@router.get(
    "/revisions/{object_id}/components",
    response_model=Page[ComponentListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_bom_revision_components",
    dependencies=[Depends(unique_query)],
)
async def list_bom_revision_components(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[BomLineQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await bom_reads.list_children(
        db,
        current,
        company_id,
        bom_id,
        object_id,
        BomRevision,
        BomComponent,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/revisions/{object_id}/outputs",
    response_model=Page[OutputListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_bom_revision_outputs",
    dependencies=[Depends(unique_query)],
)
async def list_bom_revision_outputs(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[BomLineQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await bom_reads.list_children(
        db,
        current,
        company_id,
        bom_id,
        object_id,
        BomRevision,
        BomOutput,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.post(
    "/drafts",
    response_model=BomDraftDetail,
    response_model_exclude_unset=True,
    status_code=201,
    operation_id="create_catalog_bom_draft",
)
async def create_draft(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    body: BomDraftInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, bom_id, body, idempotency_key, "create")


@router.patch(
    "/drafts/{object_id}",
    response_model=BomDraftDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_bom_draft",
)
async def update_draft(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    body: BomDraftUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, bom_id, body, idempotency_key, "update", object_id
    )


@router.post(
    "/drafts/{object_id}/publish",
    response_model=BomDraftDetail,
    response_model_exclude_unset=True,
    operation_id="publish_catalog_bom_definition",
)
async def publish_definition(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, bom_id, body, idempotency_key, "publish", object_id
    )


@router.post(
    "/revisions/{object_id}/retire",
    response_model=BomRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="retire_catalog_bom_definition",
)
async def retire_definition(
    company_id: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, bom_id, body, idempotency_key, "retire", object_id
    )
