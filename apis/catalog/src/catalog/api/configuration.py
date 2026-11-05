"""Configuration administration uses current company/field authority on every operation."""

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
from catalog.api.units import Idempotency, no_query, unique_query
from catalog.schemas.configuration import (
    AuthoringDefaults,
    AuthoringDefaultsQuery,
    CompanyDraftInput,
    ConfigurationOptionItem,
    ConfigurationOptionQuery,
    ConfigurationOptionSource,
    ConfigurationPreview,
    DraftDetail,
    DraftInput,
    DraftListItem,
    DraftPatch,
    DraftQuery,
    EffectiveConfiguration,
    EffectiveQuery,
    PublishInput,
    RevisionDetail,
    RevisionListItem,
    RevisionQuery,
    ScopeCreate,
    ScopeDetail,
    ScopeListItem,
    ScopeQuery,
)
from catalog.tasks.configuration import command, list_rows, preview, read
from catalog.tasks.configuration_resolution import resolve

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/product-configuration/options/{source}",
    response_model=Page[ConfigurationOptionItem],
    dependencies=[Depends(unique_query)],
    operation_id="catalog_configuration_reference_options",
)
async def reference_options(
    company_id: uuid.UUID,
    source: ConfigurationOptionSource,
    query: Annotated[ConfigurationOptionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[ConfigurationOptionItem]:
    from catalog.tasks.configuration_options import options

    return await options(
        db,
        current,
        company_id,
        source,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


async def write(
    request: Request,
    current: Actor,
    company: uuid.UUID,
    body: ScopeCreate | CompanyDraftInput | DraftPatch | PublishInput,
    key: str,
    object_id: uuid.UUID | None = None,
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory, current, company, body, key, object_id=object_id
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json", exclude_unset=True),
        headers={"Idempotency-Replayed": str(result.replayed).lower(), "Cache-Control": "no-store"},
    )


@router.post(
    "/product-configuration-scopes",
    response_model=ScopeDetail,
    response_model_exclude_unset=True,
    operation_id="create_scope_catalog_configuration",
    status_code=201,
)
async def create_scope(
    company_id: uuid.UUID,
    body: ScopeCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key)


@router.post(
    "/product-configurations/company",
    response_model=DraftDetail,
    response_model_exclude_unset=True,
    operation_id="create_company_draft_catalog_configuration",
    status_code=201,
)
async def create_company_draft(
    company_id: uuid.UUID,
    body: CompanyDraftInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key)


@router.post(
    "/product-configurations",
    response_model=DraftDetail,
    response_model_exclude_unset=True,
    operation_id="create_draft_catalog_configuration",
    status_code=201,
)
async def create_draft(
    company_id: uuid.UUID,
    body: DraftInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key)


@router.patch(
    "/product-configurations/{object_id}",
    response_model=DraftDetail,
    response_model_exclude_unset=True,
    operation_id="update_draft_catalog_configuration",
    status_code=200,
)
async def update_draft(
    company_id: uuid.UUID,
    body: DraftPatch,
    request: Request,
    idempotency_key: Idempotency,
    object_id: uuid.UUID,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key, object_id)


@router.post(
    "/product-configurations/{object_id}/publish",
    response_model=RevisionDetail,
    response_model_exclude_unset=True,
    operation_id="publish_draft_catalog_configuration",
    status_code=201,
)
async def publish_draft(
    company_id: uuid.UUID,
    body: PublishInput,
    request: Request,
    idempotency_key: Idempotency,
    object_id: uuid.UUID,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, body, idempotency_key, object_id)


@router.get(
    "/product-configuration-scopes/{object_id}",
    response_model=ScopeDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_configuration_scope",
)
async def get_scope(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, "scope", object_id)


@router.get(
    "/product-configurations/{object_id}",
    response_model=DraftDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_configuration_draft",
)
async def get_draft(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, "draft", object_id)


@router.get(
    "/product-configuration-revisions/{object_id}",
    response_model=RevisionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_configuration_revision",
)
async def get_revision(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, "revision", object_id)


@router.get(
    "/product-configuration-scopes",
    response_model=Page[ScopeListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_configuration_scope",
)
async def list_scope(
    company_id: uuid.UUID,
    query: Annotated[ScopeQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        "scope",
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/product-configuration-scopes/{scope_id}/drafts",
    response_model=Page[DraftListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_configuration_draft",
)
async def list_draft(
    company_id: uuid.UUID,
    query: Annotated[DraftQuery, Query()],
    request: Request,
    scope_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        "draft",
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        scope_id,
    )


@router.get(
    "/product-configuration-scopes/{scope_id}/revisions",
    response_model=Page[RevisionListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_configuration_revision",
)
async def list_revision(
    company_id: uuid.UUID,
    query: Annotated[RevisionQuery, Query()],
    request: Request,
    scope_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        "revision",
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        scope_id,
    )


@router.get(
    "/product-configurations/{object_id}/preview",
    response_model=ConfigurationPreview,
    operation_id="preview_catalog_configuration",
)
async def preview_draft(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ConfigurationPreview:
    no_query(request)
    return await preview(db, current, company_id, object_id)


@router.get(
    "/product-configuration/effective",
    response_model=EffectiveConfiguration,
    dependencies=[Depends(unique_query)],
    operation_id="resolve_catalog_configuration",
)
@router.get(
    "/catalog-defaults",
    response_model=EffectiveConfiguration,
    dependencies=[Depends(unique_query)],
    operation_id="resolve_catalog_defaults",
)
async def effective(
    company_id: uuid.UUID,
    query: Annotated[EffectiveQuery, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> EffectiveConfiguration:
    return await resolve(db, current, company_id, query)


@router.get(
    "/item-groups/{group_id}/defaults",
    response_model=EffectiveConfiguration,
    dependencies=[Depends(unique_query)],
    operation_id="resolve_catalog_group_defaults",
)
async def group_defaults(
    company_id: uuid.UUID,
    group_id: uuid.UUID,
    query: Annotated[EffectiveQuery, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> EffectiveConfiguration:
    from billing_platform.errors import ValidationFailedError

    if query.group_id is not None and query.group_id != group_id:
        raise ValidationFailedError("group path and query disagree")
    return await resolve(db, current, company_id, query.model_copy(update={"group_id": group_id}))


@router.get(
    "/product-configuration/authoring-defaults",
    response_model=AuthoringDefaults,
    dependencies=[Depends(unique_query)],
    operation_id="catalog_configuration_authoring_defaults",
)
async def authoring_defaults(
    company_id: uuid.UUID,
    query: Annotated[AuthoringDefaultsQuery, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> AuthoringDefaults:
    from catalog.tasks.configuration_access import ConfigurationAccess
    from catalog.tasks.configuration_authoring import suggestions

    return await suggestions(ConfigurationAccess(db, current, company_id), query)
