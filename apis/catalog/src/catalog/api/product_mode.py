"""Live company Product Configuration authoring control."""

import uuid

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, no_query
from catalog.schemas.product_mode import (
    ProductModeCommit,
    ProductModeDetail,
    ProductModePreview,
    ProductModeRequest,
)
from catalog.tasks import product_mode

router = APIRouter(
    prefix="/v1/companies/{company_id}/product-configuration/authoring",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get("", response_model=ProductModeDetail, operation_id="get_catalog_product_authoring_mode")
async def read(
    company_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ProductModeDetail:
    no_query(request)
    return await product_mode.read(db, current, company_id)


@router.post(
    "/preview",
    response_model=ProductModePreview,
    operation_id="preview_catalog_product_authoring_mode",
)
async def preview(
    company_id: uuid.UUID,
    body: ProductModeRequest,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ProductModePreview:
    no_query(request)
    return await product_mode.preview(
        db,
        current,
        company_id,
        body,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.patch(
    "", response_model=ProductModeDetail, operation_id="update_catalog_product_authoring_mode"
)
async def update(
    company_id: uuid.UUID,
    body: ProductModeCommit,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await product_mode.command(
        request.app.state.session_factory,
        current,
        company_id,
        body,
        idempotency_key,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json"),
        headers={"Idempotency-Replayed": str(result.replayed).lower(), "Cache-Control": "no-store"},
    )
