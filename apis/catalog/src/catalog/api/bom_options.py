"""BOM lookups use explicit scoped sources; no arbitrary entity browsing."""

import uuid
from typing import Annotated, Literal

from billing_platform.errors import ErrorEnvelope, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import no_query, unique_query
from catalog.schemas.boms import (
    BomReferenceOption,
    BomReferenceQuery,
    BomRevisionOptionsQuery,
    BomStoredReference,
    BomUnitOption,
    BomUnitQuery,
)
from catalog.schemas.configuration import ConfigurationOptionItem, ConfigurationOptionQuery
from catalog.tasks import bom_options
from catalog.tasks.configuration_options import options

router = APIRouter(
    prefix="/v1/companies/{company_id}/boms/options",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 422, 503)},
)


@router.get(
    "/references/{source}/{object_id}",
    response_model=BomStoredReference,
    operation_id="get_catalog_bom_stored_reference",
    dependencies=[Depends(no_query)],
)
async def stored_reference(
    company_id: uuid.UUID,
    source: Literal["goods", "units", "routes", "revisions"],
    object_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BomStoredReference:
    return await bom_options.stored_reference(db, current, company_id, source, object_id)


@router.get(
    "/goods",
    response_model=Page[ConfigurationOptionItem],
    operation_id="list_catalog_bom_goods_options",
    dependencies=[Depends(unique_query)],
)
async def goods_options(
    company_id: uuid.UUID,
    query: Annotated[ConfigurationOptionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[ConfigurationOptionItem]:
    if query.kind not in {None, "GOODS"}:
        raise ValidationFailedError("BOM physical rows require goods SKUs")
    query = query.model_copy(update={"kind": "GOODS"})
    return await options(
        db,
        current,
        company_id,
        "items",
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        owner_permission="bom.read",
        owner_entity="catalog.bom",
    )


@router.get(
    "/units",
    response_model=Page[BomUnitOption],
    operation_id="list_catalog_bom_unit_options",
    dependencies=[Depends(unique_query)],
)
async def unit_options(
    company_id: uuid.UUID,
    query: Annotated[BomUnitQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BomUnitOption]:
    return await bom_options.unit_options(
        db,
        current,
        company_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/routes",
    response_model=Page[BomReferenceOption],
    operation_id="list_catalog_bom_route_options",
    dependencies=[Depends(unique_query)],
)
async def route_options(
    company_id: uuid.UUID,
    query: Annotated[BomReferenceQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BomReferenceOption]:
    return await bom_options.revision_options(
        db,
        current,
        company_id,
        "routes",
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/revisions",
    response_model=Page[BomReferenceOption],
    operation_id="list_catalog_bom_revision_options",
    dependencies=[Depends(unique_query)],
)
async def revision_options(
    company_id: uuid.UUID,
    query: Annotated[BomRevisionOptionsQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BomReferenceOption]:
    return await bom_options.revision_options(
        db,
        current,
        company_id,
        "boms",
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
