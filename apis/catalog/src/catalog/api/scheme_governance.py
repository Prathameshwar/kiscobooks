"""Reviewed scheme policy and dated family classification commands."""

import uuid

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, no_query
from catalog.models.products import ProductFamily
from catalog.schemas.classification import SchemeDetail
from catalog.schemas.product_authoring import CategoryAssignmentInput, CategoryAssignmentPreview
from catalog.schemas.scheme_governance import (
    SchemeTransition,
    SchemeTransitionCommit,
    SchemeTransitionPreview,
)
from catalog.tasks import category_schedule, scheme_governance
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.product_commands import ProductWork

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.post(
    "/category-schemes/{object_id}/transition-preview",
    response_model=SchemeTransitionPreview,
    operation_id="preview_catalog_scheme_transition",
)
async def scheme_preview(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: SchemeTransition,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> SchemeTransitionPreview:
    no_query(request)
    return await scheme_governance.preview(
        ConfigurationAccess(db, current, company_id),
        object_id,
        body,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.post(
    "/category-schemes/{object_id}/transition",
    response_model=SchemeDetail,
    response_model_exclude_unset=True,
    operation_id="transition_catalog_scheme",
)
async def scheme_transition(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: SchemeTransitionCommit,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await scheme_governance.transition(
        request.app.state.session_factory,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
    return JSONResponse(
        result.value.model_dump(mode="json", exclude_unset=True),
        status_code=result.status,
        headers={"Cache-Control": "no-store", "Idempotency-Replayed": str(result.replayed).lower()},
    )


@router.post(
    "/product-families/{object_id}/category-preview",
    response_model=CategoryAssignmentPreview,
    operation_id="preview_catalog_family_categories",
)
async def category_preview(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: CategoryAssignmentInput,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CategoryAssignmentPreview:
    no_query(request)
    access = ConfigurationAccess(db, current, company_id)
    family = await access.reference(ProductFamily, object_id)
    work = ProductWork(db, current, company_id, family, None, access)
    return await category_schedule.prepare(
        work, body, request.app.state.settings.actor_signing_secret.get_secret_value().encode()
    )
