"""Explicit review/adoption of product definitions sourced from Identity."""

import uuid

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, command_response, no_query
from catalog.schemas.field_adoption import AdoptionInput, AdoptionResult, AdoptionReview
from catalog.tasks.product_field_rollout import adopt, preview

router = APIRouter(
    prefix="/v1/companies/{company_id}/entities/{entity_type}/custom-field-adoption",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.post(
    "/preview", response_model=AdoptionReview, operation_id="preview_product_custom_fields"
)
async def review(
    company_id: uuid.UUID,
    entity_type: str,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> AdoptionReview:
    no_query(request)
    return await preview(
        db,
        current,
        company_id,
        entity_type,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.post("", response_model=AdoptionResult, operation_id="adopt_product_custom_fields")
async def commit(
    company_id: uuid.UUID,
    entity_type: str,
    body: AdoptionInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await adopt(
        request.app.state.session_factory,
        current,
        company_id,
        entity_type,
        body,
        idempotency_key,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
    return command_response(request, result, created=False)
