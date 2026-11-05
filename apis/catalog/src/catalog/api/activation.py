"""Reviewed SKU activation; no stock creation or invoice determination."""

import uuid

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.pricing import exact_pricing_errors
from catalog.api.units import Idempotency, no_query
from catalog.schemas.activation import ActivationCommit, ActivationInput, ActivationPreview
from catalog.schemas.product_authoring import AuthoringResult
from catalog.tasks.activation import activate, prepare
from catalog.tasks.product_commands import ProductWork, execute
from catalog.tasks.product_requirements import product_work

router = APIRouter(
    prefix="/v1/companies/{company_id}/items/{item_id}",
    dependencies=[Depends(exact_pricing_errors)],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)},
)


@router.post(
    "/activation-preview",
    response_model=ActivationPreview,
    operation_id="preview_catalog_item_activation",
)
async def preview(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ActivationInput,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ActivationPreview:
    no_query(request)
    result, _ = await prepare(
        await product_work(db, current, company_id, item_id),
        body.as_of,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
    return result


@router.post("/activate", response_model=AuthoringResult, operation_id="activate_catalog_item")
async def commit(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ActivationCommit,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    bucket = "activate:" + current.tenant_id.hex + company_id.hex + current.user_id.hex
    if not request.app.state.pricing_limiter.allow(bucket, limit=30):
        raise HTTPException(status_code=429, detail="activation write rate exceeded")

    async def apply(work: ProductWork, command: ActivationCommit) -> None:
        await activate(
            work,
            command,
            request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        )

    result = await execute(
        request.app.state.session_factory,
        current,
        company_id,
        item_id,
        body,
        key,
        "activate",
        apply,
        item=True,
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json"),
        headers={"Idempotency-Replayed": str(result.replayed).lower(), "Cache-Control": "no-store"},
    )
