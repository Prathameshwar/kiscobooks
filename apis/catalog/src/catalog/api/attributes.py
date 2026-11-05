"""Protected native attribute master routes."""

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
from catalog.api.classification import write
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, no_query, unique_query
from catalog.schemas.attributes import (
    AttributeDefinitionCreate,
    AttributeDefinitionDetail,
    AttributeDefinitionListItem,
    AttributeDefinitionQuery,
    AttributeDefinitionUpdate,
    AttributeOptionCreate,
    AttributeOptionDetail,
    AttributeOptionListItem,
    AttributeOptionQuery,
    AttributeOptionUpdate,
    AttributeSetCreate,
    AttributeSetDetail,
    AttributeSetListItem,
    AttributeSetQuery,
    AttributeSetUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.attributes import ATTRIBUTE_DEFINITION, ATTRIBUTE_OPTION, ATTRIBUTE_SET
from catalog.tasks.classification import list_rows, read

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/attribute-definitions",
    response_model=Page[AttributeDefinitionListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_attribute_definition",
    dependencies=[Depends(unique_query)],
)
async def list_attribute_definition(
    company_id: uuid.UUID,
    query: Annotated[AttributeDefinitionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        ATTRIBUTE_DEFINITION,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/attribute-definitions/{object_id}",
    response_model=AttributeDefinitionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_attribute_definition",
)
async def get_attribute_definition(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, ATTRIBUTE_DEFINITION)


@router.post(
    "/attribute-definitions",
    response_model=AttributeDefinitionDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_attribute_definition",
    status_code=201,
)
async def create_attribute_definition(
    company_id: uuid.UUID,
    body: AttributeDefinitionCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, ATTRIBUTE_DEFINITION, body, idempotency_key, "create"
    )


@router.patch(
    "/attribute-definitions/{object_id}",
    response_model=AttributeDefinitionDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_attribute_definition",
)
async def update_attribute_definition(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: AttributeDefinitionUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        ATTRIBUTE_DEFINITION,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/attribute-definitions/{object_id}/activate",
    response_model=AttributeDefinitionDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_attribute_definition",
)
async def activate_attribute_definition(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        ATTRIBUTE_DEFINITION,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/attribute-definitions/{object_id}/deactivate",
    response_model=AttributeDefinitionDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_attribute_definition",
)
async def deactivate_attribute_definition(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        ATTRIBUTE_DEFINITION,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )


@router.get(
    "/attribute-options",
    response_model=Page[AttributeOptionListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_attribute_option",
    dependencies=[Depends(unique_query)],
)
async def list_attribute_option(
    company_id: uuid.UUID,
    query: Annotated[AttributeOptionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        ATTRIBUTE_OPTION,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/attribute-options/{object_id}",
    response_model=AttributeOptionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_attribute_option",
)
async def get_attribute_option(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, ATTRIBUTE_OPTION)


@router.post(
    "/attribute-options",
    response_model=AttributeOptionDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_attribute_option",
    status_code=201,
)
async def create_attribute_option(
    company_id: uuid.UUID,
    body: AttributeOptionCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, ATTRIBUTE_OPTION, body, idempotency_key, "create"
    )


@router.patch(
    "/attribute-options/{object_id}",
    response_model=AttributeOptionDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_attribute_option",
)
async def update_attribute_option(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: AttributeOptionUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, ATTRIBUTE_OPTION, body, idempotency_key, "update", object_id
    )


@router.post(
    "/attribute-options/{object_id}/activate",
    response_model=AttributeOptionDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_attribute_option",
)
async def activate_attribute_option(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, ATTRIBUTE_OPTION, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/attribute-options/{object_id}/deactivate",
    response_model=AttributeOptionDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_attribute_option",
)
async def deactivate_attribute_option(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        ATTRIBUTE_OPTION,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )


@router.get(
    "/attribute-sets",
    response_model=Page[AttributeSetListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_attribute_set",
    dependencies=[Depends(unique_query)],
)
async def list_attribute_set(
    company_id: uuid.UUID,
    query: Annotated[AttributeSetQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        ATTRIBUTE_SET,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/attribute-sets/{object_id}",
    response_model=AttributeSetDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_attribute_set",
)
async def get_attribute_set(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, ATTRIBUTE_SET)


@router.post(
    "/attribute-sets",
    response_model=AttributeSetDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_attribute_set",
    status_code=201,
)
async def create_attribute_set(
    company_id: uuid.UUID,
    body: AttributeSetCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, ATTRIBUTE_SET, body, idempotency_key, "create")


@router.patch(
    "/attribute-sets/{object_id}",
    response_model=AttributeSetDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_attribute_set",
)
async def update_attribute_set(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: AttributeSetUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, ATTRIBUTE_SET, body, idempotency_key, "update", object_id
    )


@router.post(
    "/attribute-sets/{object_id}/activate",
    response_model=AttributeSetDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_attribute_set",
)
async def activate_attribute_set(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, ATTRIBUTE_SET, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/attribute-sets/{object_id}/deactivate",
    response_model=AttributeSetDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_attribute_set",
)
async def deactivate_attribute_set(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, ATTRIBUTE_SET, body, idempotency_key, "deactivate", object_id
    )
