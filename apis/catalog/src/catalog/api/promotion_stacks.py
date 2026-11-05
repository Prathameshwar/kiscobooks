"""Protected stack-definition drafts and immutable publication history."""

import uuid
from typing import Annotated

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
from catalog.schemas.promotion_authoring import (
    StackAuthoringContext,
    StackDraftDetail,
    StackDraftInput,
    StackDraftListItem,
    StackDraftUpdate,
    StackPolicyDetail,
    StackPolicyListItem,
    StackQuery,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks import promotion_stacks
from catalog.tasks.field_context import load_field_context

router = APIRouter(
    prefix="/v1/companies/{company_id}/promotion-stack-policies",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/authoring-context",
    response_model=StackAuthoringContext,
    operation_id="get_promotion_stack_authoring_context",
    dependencies=[Depends(no_query)],
)
async def context(
    company_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> StackAuthoringContext:
    context = await load_field_context(db, current, company_id, "catalog.promotion_stack_draft")
    return StackAuthoringContext(
        company_id=company_id, enabled="sales_promotions" in context.features
    )


@router.get(
    "/drafts",
    response_model=Page[StackDraftListItem],
    response_model_exclude_unset=True,
    operation_id="list_promotion_stack_drafts",
    dependencies=[Depends(unique_query)],
)
async def drafts(
    company_id: uuid.UUID,
    query: Annotated[StackQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await promotion_stacks.list_rows(
        db,
        current,
        company_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/revisions",
    response_model=Page[StackPolicyListItem],
    response_model_exclude_unset=True,
    operation_id="list_promotion_stack_revisions",
    dependencies=[Depends(unique_query)],
)
async def revisions(
    company_id: uuid.UUID,
    query: Annotated[StackQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await promotion_stacks.list_rows(
        db,
        current,
        company_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        published=True,
    )


@router.get(
    "/drafts/{object_id}",
    response_model=StackDraftDetail,
    response_model_exclude_unset=True,
    operation_id="get_promotion_stack_draft",
    dependencies=[Depends(no_query)],
)
async def draft(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    return await promotion_stacks.read(db, current, company_id, object_id)


@router.get(
    "/revisions/{object_id}",
    response_model=StackPolicyDetail,
    response_model_exclude_unset=True,
    operation_id="get_promotion_stack_revision",
    dependencies=[Depends(no_query)],
)
async def revision(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    return await promotion_stacks.read(db, current, company_id, object_id, published=True)


@router.post(
    "/drafts",
    response_model=StackDraftDetail,
    response_model_exclude_unset=True,
    status_code=201,
    operation_id="create_promotion_stack_draft",
)
async def create(
    company_id: uuid.UUID,
    body: StackDraftInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await promotion_stacks.command(
        request.app.state.session_factory, current, company_id, body, idempotency_key, "create"
    )
    return command_response(request, result, created=True)


@router.patch(
    "/drafts/{object_id}",
    response_model=StackDraftDetail,
    response_model_exclude_unset=True,
    operation_id="update_promotion_stack_draft",
)
async def update(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: StackDraftUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await promotion_stacks.command(
        request.app.state.session_factory,
        current,
        company_id,
        body,
        idempotency_key,
        "update",
        object_id,
    )
    return command_response(request, result, created=False)


@router.post(
    "/drafts/{object_id}/publish",
    response_model=StackDraftDetail,
    response_model_exclude_unset=True,
    operation_id="publish_promotion_stack_draft",
)
async def publish(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await promotion_stacks.command(
        request.app.state.session_factory,
        current,
        company_id,
        body,
        idempotency_key,
        "publish",
        object_id,
    )
    return command_response(request, result, created=False)
