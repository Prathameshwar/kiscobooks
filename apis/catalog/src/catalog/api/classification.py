"""Group, category-scheme and category routes; services own policy and transactions."""

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
from catalog.schemas.classification import (
    CategoryCreate,
    CategoryDetail,
    CategoryListItem,
    CategoryQuery,
    CategoryReparent,
    CategoryUpdate,
    GroupChildrenQuery,
    GroupCreate,
    GroupDetail,
    GroupListItem,
    GroupParentListItem,
    GroupParentQuery,
    GroupQuery,
    GroupReparent,
    GroupUpdate,
    SchemeCreate,
    SchemeDetail,
    SchemeListItem,
    SchemeQuery,
    SchemeUpdate,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.classification import (
    CATEGORY,
    GROUP,
    SCHEME,
    Classification,
    command,
    list_children,
    list_parent_history,
    list_rows,
    read,
)

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


async def write(
    request: Request,
    current: Actor,
    company_id: uuid.UUID,
    spec: Classification,
    body: BaseModel,
    key: str,
    action: Literal["create", "update", "activate", "deactivate", "move", "assign"],
    object_id: uuid.UUID | None = None,
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        spec,
        key=key,
        body=body,
        action=action,
        object_id=object_id,
    )
    return command_response(request, result, created=action == "create")


@router.post(
    "/item-groups",
    response_model=GroupDetail,
    status_code=201,
    response_model_exclude_unset=True,
    operation_id="create_catalog_group",
)
async def create_group(
    company_id: uuid.UUID,
    body: GroupCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, GROUP, body, idempotency_key, "create")


@router.get(
    "/item-groups",
    response_model=Page[GroupListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_groups",
    dependencies=[Depends(unique_query)],
)
async def list_groups(
    company_id: uuid.UUID,
    query: Annotated[GroupQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        GROUP,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/item-groups/{object_id}",
    response_model=GroupDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_group",
)
async def get_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, GROUP)


@router.patch(
    "/item-groups/{object_id}",
    response_model=GroupDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_group",
)
async def update_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: GroupUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, GROUP, body, idempotency_key, "update", object_id
    )


@router.post(
    "/item-groups/{object_id}/activate",
    response_model=GroupDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_group",
)
async def activate_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, GROUP, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/item-groups/{object_id}/deactivate",
    response_model=GroupDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_group",
)
async def deactivate_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, GROUP, body, idempotency_key, "deactivate", object_id
    )


@router.post(
    "/item-groups/{object_id}/reparent",
    response_model=GroupDetail,
    response_model_exclude_unset=True,
    operation_id="move_catalog_group",
)
async def move_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: GroupReparent,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, GROUP, body, idempotency_key, "move", object_id
    )


@router.post(
    "/category-schemes",
    response_model=SchemeDetail,
    status_code=201,
    response_model_exclude_unset=True,
    operation_id="create_catalog_scheme",
)
async def create_scheme(
    company_id: uuid.UUID,
    body: SchemeCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, SCHEME, body, idempotency_key, "create")


@router.get(
    "/category-schemes",
    response_model=Page[SchemeListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_schemes",
    dependencies=[Depends(unique_query)],
)
async def list_schemes(
    company_id: uuid.UUID,
    query: Annotated[SchemeQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        SCHEME,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/category-schemes/{object_id}",
    response_model=SchemeDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_scheme",
)
async def get_scheme(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, SCHEME)


@router.patch(
    "/category-schemes/{object_id}",
    response_model=SchemeDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_scheme",
)
async def update_scheme(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: SchemeUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, SCHEME, body, idempotency_key, "update", object_id
    )


@router.post(
    "/category-schemes/{object_id}/activate",
    response_model=SchemeDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_scheme",
)
async def activate_scheme(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, SCHEME, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/category-schemes/{object_id}/deactivate",
    response_model=SchemeDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_scheme",
)
async def deactivate_scheme(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, SCHEME, body, idempotency_key, "deactivate", object_id
    )


@router.post(
    "/item-categories",
    response_model=CategoryDetail,
    status_code=201,
    response_model_exclude_unset=True,
    operation_id="create_catalog_category",
)
async def create_category(
    company_id: uuid.UUID,
    body: CategoryCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, CATEGORY, body, idempotency_key, "create")


@router.get(
    "/item-categories",
    response_model=Page[CategoryListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_categorys",
    dependencies=[Depends(unique_query)],
)
async def list_categorys(
    company_id: uuid.UUID,
    query: Annotated[CategoryQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        CATEGORY,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/item-categories/{object_id}",
    response_model=CategoryDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_category",
)
async def get_category(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, CATEGORY)


@router.patch(
    "/item-categories/{object_id}",
    response_model=CategoryDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_category",
)
async def update_category(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: CategoryUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, CATEGORY, body, idempotency_key, "update", object_id
    )


@router.post(
    "/item-categories/{object_id}/activate",
    response_model=CategoryDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_category",
)
async def activate_category(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, CATEGORY, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/item-categories/{object_id}/deactivate",
    response_model=CategoryDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_category",
)
async def deactivate_category(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, CATEGORY, body, idempotency_key, "deactivate", object_id
    )


@router.post(
    "/item-categories/{object_id}/reparent",
    response_model=CategoryDetail,
    response_model_exclude_unset=True,
    operation_id="move_catalog_category",
)
async def move_category(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: CategoryReparent,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, CATEGORY, body, idempotency_key, "move", object_id
    )


@router.get(
    "/item-groups/{object_id}/parents",
    response_model=Page[GroupParentListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_group_parent_history",
    dependencies=[Depends(unique_query)],
)
async def group_parent_history(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[GroupParentQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[GroupParentListItem]:
    return await list_parent_history(
        db,
        current,
        company_id,
        object_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/item-groups/{object_id}/children",
    response_model=Page[GroupListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_group_children",
    dependencies=[Depends(unique_query)],
)
async def group_children(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[GroupChildrenQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_children(
        db,
        current,
        company_id,
        object_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
