"""Advanced options, private drafts and native Profile/SKU definitions."""

import uuid
from typing import Annotated, Literal

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.pricing import exact_pricing_errors
from catalog.api.simple_product_creation import context as opening_context
from catalog.api.simple_product_creation import owners as opening_owners
from catalog.api.units import no_query, unique_query
from catalog.schemas.advanced_product_creation import (
    AdvancedCreationOptions,
    AdvancedDefinitionCreate,
    AdvancedDefinitionResult,
    AdvancedDefinitionStatus,
    AdvancedDraftDetail,
    AdvancedDraftListItem,
    AdvancedDraftRevision,
    AdvancedDraftSave,
    AdvancedOpeningCheck,
    AdvancedOpeningInput,
    AdvancedOpeningSubmit,
    AdvancedReadinessRequest,
    AdvancedSkuActivate,
    AdvancedSkuPublish,
    AdvancedSkuReadiness,
    AdvancedSkuSetup,
)
from catalog.schemas.products import FamilyCreate
from catalog.tasks import advanced_creation_opening as opening_tasks
from catalog.tasks import advanced_creation_steps as steps
from catalog.tasks import advanced_product_drafts as drafts
from catalog.tasks.advanced_creation_readiness import read as read_readiness
from catalog.tasks.advanced_product_creation import read_status
from catalog.tasks.advanced_product_options import context
from catalog.tasks.products import command as product_command

CreateKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=64)]
ExpectedVersion = Annotated[int, Header(alias="If-Match", ge=1)]


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/v1/companies/{company_id}/advanced-product-creations",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)},
    dependencies=[Depends(unique_query), Depends(no_store), Depends(exact_pricing_errors)],
)


def limit(request: Request, current: Actor, company: uuid.UUID) -> None:
    if not request.app.state.pricing_limiter.allow(
        f"advanced-draft:{current.tenant_id}:{company}:{current.user_id}", limit=120
    ):
        raise HTTPException(status_code=429, detail="product draft rate exceeded")


@router.get(
    "/options",
    response_model=AdvancedCreationOptions,
    operation_id="get_advanced_product_creation_options",
)
async def options(
    company_id: uuid.UUID,
    request: Request,
    kind: Literal["GOODS", "SERVICE"] = "GOODS",
    group_id: uuid.UUID | None = None,
    product_type_revision_id: uuid.UUID | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> AdvancedCreationOptions:
    if set(request.query_params) - {"kind", "group_id", "product_type_revision_id"}:
        from billing_platform.errors import ValidationFailedError

        raise ValidationFailedError("Unknown product options query parameter")
    return await context(
        db,
        current,
        company_id,
        request,
        kind=kind,
        group_id=group_id,
        product_type_revision_id=product_type_revision_id,
    )


@router.get(
    "/drafts",
    response_model=list[AdvancedDraftListItem],
    operation_id="list_advanced_product_drafts",
)
async def list_drafts(
    company_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> list[AdvancedDraftListItem]:
    no_query(request)
    return await drafts.list_owned(db, current, company_id, request)


@router.post(
    "/drafts",
    response_model=AdvancedDraftDetail,
    status_code=201,
    operation_id="create_advanced_product_draft",
)
async def create_draft(
    company_id: uuid.UUID,
    body: AdvancedDraftSave,
    request: Request,
    key: CreateKey,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> JSONResponse:
    no_query(request)
    limit(request, current, company_id)
    value, replayed = await drafts.create(db, current, company_id, request, body, key)
    return JSONResponse(
        status_code=200 if replayed else 201,
        content=value.model_dump(mode="json"),
        headers={"Cache-Control": "no-store", "Idempotency-Replayed": str(replayed).lower()},
    )


@router.get(
    "/drafts/{draft_id}",
    response_model=AdvancedDraftDetail,
    operation_id="get_advanced_product_draft",
)
async def get_draft(
    company_id: uuid.UUID,
    draft_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> AdvancedDraftDetail:
    no_query(request)
    return await drafts.read(db, current, company_id, request, draft_id)


@router.put(
    "/drafts/{draft_id}",
    response_model=AdvancedDraftDetail,
    operation_id="replace_advanced_product_draft",
)
async def replace_draft(
    company_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: AdvancedDraftRevision,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> AdvancedDraftDetail:
    no_query(request)
    limit(request, current, company_id)
    return await drafts.replace(db, current, company_id, request, draft_id, body)


@router.delete(
    "/drafts/{draft_id}",
    status_code=204,
    operation_id="delete_advanced_product_draft",
)
async def delete_draft(
    company_id: uuid.UUID,
    draft_id: uuid.UUID,
    request: Request,
    expected_version: ExpectedVersion,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Response:
    no_query(request)
    limit(request, current, company_id)
    await drafts.delete(db, current, company_id, draft_id, expected_version)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post(
    "/definitions",
    response_model=AdvancedDefinitionResult,
    status_code=201,
    operation_id="create_advanced_product_definition",
)
async def create_definition(
    company_id: uuid.UUID,
    body: AdvancedDefinitionCreate,
    request: Request,
    key: CreateKey,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    limit(request, current, company_id)
    family = FamilyCreate(**body.profile.model_dump(), default_item=body.skus[0].item)
    result = await product_command(
        request.app.state.session_factory,
        current,
        company_id,
        family,
        key,
        advanced_definition=body,
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json", exclude_unset=True),
        headers={"Cache-Control": "no-store", "Idempotency-Replayed": str(result.replayed).lower()},
    )


@router.get(
    "/definitions/{creation_id}",
    response_model=AdvancedDefinitionStatus,
    operation_id="get_advanced_product_definition",
)
async def get_definition(
    company_id: uuid.UUID,
    creation_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> AdvancedDefinitionStatus:
    no_query(request)
    return await read_status(db, current, company_id, creation_id)


@router.post(
    "/definitions/{creation_id}/skus/{item_id}/setup",
    response_model=AdvancedDefinitionStatus,
    operation_id="setup_advanced_product_sku",
)
async def setup_sku(
    company_id: uuid.UUID,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: AdvancedSkuSetup,
    request: Request,
    key: CreateKey,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    limit(request, current, company_id)
    result = await steps.setup(
        request.app.state.session_factory, current, company_id, creation_id, item_id, body, key
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json"),
        headers={"Cache-Control": "no-store", "Idempotency-Replayed": str(result.replayed).lower()},
    )


@router.post(
    "/definitions/{creation_id}/skus/{item_id}/publish-prices",
    response_model=AdvancedDefinitionStatus,
    operation_id="publish_advanced_product_sku_prices",
)
async def publish_sku_prices(
    company_id: uuid.UUID,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: AdvancedSkuPublish,
    request: Request,
    key: CreateKey,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    limit(request, current, company_id)
    result = await steps.publish(
        request.app.state.session_factory, current, company_id, creation_id, item_id, body, key
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json"),
        headers={"Cache-Control": "no-store", "Idempotency-Replayed": str(result.replayed).lower()},
    )


@router.post(
    "/definitions/{creation_id}/skus/{item_id}/readiness",
    response_model=AdvancedSkuReadiness,
    operation_id="get_advanced_product_sku_readiness",
)
async def sku_readiness(
    company_id: uuid.UUID,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: AdvancedReadinessRequest,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> AdvancedSkuReadiness:
    no_query(request)
    return await read_readiness(
        db,
        current,
        company_id,
        creation_id,
        item_id,
        body.as_of,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.post(
    "/definitions/{creation_id}/skus/{item_id}/activate",
    response_model=AdvancedDefinitionStatus,
    operation_id="activate_advanced_product_sku",
)
async def activate_sku(
    company_id: uuid.UUID,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: AdvancedSkuActivate,
    request: Request,
    key: CreateKey,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    limit(request, current, company_id)
    result = await steps.activate(
        request.app.state.session_factory,
        current,
        company_id,
        creation_id,
        item_id,
        body,
        key,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json"),
        headers={"Cache-Control": "no-store", "Idempotency-Replayed": str(result.replayed).lower()},
    )


@router.post(
    "/definitions/{creation_id}/skus/{item_id}/opening-preflight",
    response_model=AdvancedOpeningCheck,
    operation_id="check_advanced_product_sku_opening",
)
async def opening_preflight(
    company_id: uuid.UUID,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: AdvancedOpeningInput,
    request: Request,
    current: Actor = Depends(actor),
) -> AdvancedOpeningCheck:
    no_query(request)
    limit(request, current, company_id)
    check, _, _ = await opening_tasks.preflight(
        request.app.state.session_factory,
        current,
        opening_context(request, company_id, current),
        creation_id,
        item_id,
        body,
        opening_owners(request),
    )
    return check


@router.post(
    "/definitions/{creation_id}/skus/{item_id}/opening",
    response_model=AdvancedDefinitionStatus,
    operation_id="submit_advanced_product_sku_opening",
)
async def submit_opening(
    company_id: uuid.UUID,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: AdvancedOpeningSubmit,
    request: Request,
    key: CreateKey,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    limit(request, current, company_id)
    result = await opening_tasks.submit(
        request.app.state.session_factory,
        current,
        opening_context(request, company_id, current),
        creation_id,
        item_id,
        body,
        key,
        opening_owners(request),
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json"),
        headers={"Cache-Control": "no-store", "Idempotency-Replayed": str(result.replayed).lower()},
    )


@router.post(
    "/definitions/{creation_id}/skus/{item_id}/opening/advance",
    response_model=AdvancedDefinitionStatus,
    operation_id="advance_advanced_product_sku_opening",
)
async def advance_opening(
    company_id: uuid.UUID,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
) -> AdvancedDefinitionStatus:
    no_query(request)
    limit(request, current, company_id)
    return await opening_tasks.advance(
        request.app.state.session_factory,
        current,
        opening_context(request, company_id, current),
        creation_id,
        item_id,
        opening_owners(request),
    )
