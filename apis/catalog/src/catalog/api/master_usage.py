"""Protected local master references, selected and paginated by relation."""

import uuid
from typing import Annotated

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import no_query, unique_query
from catalog.schemas.master_references import MasterEntity
from catalog.schemas.master_usage import UsageCatalog, UsagePage, UsageQuery
from catalog.tasks.master_usage import list_usage, relation_catalog

router = APIRouter(
    prefix="/v1/companies/{company_id}/masters/{entity_type}/{target_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 422, 503)},
)


@router.get(
    "/usage-relations",
    response_model=UsageCatalog,
    operation_id="list_catalog_master_usage_relations",
)
async def relations(
    company_id: uuid.UUID,
    entity_type: MasterEntity,
    target_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> UsageCatalog:
    no_query(request)
    return await relation_catalog(db, current, company_id, entity_type, target_id)


@router.get(
    "/usage",
    response_model=UsagePage,
    operation_id="list_catalog_master_usage",
    dependencies=[Depends(unique_query)],
)
async def listing(
    company_id: uuid.UUID,
    entity_type: MasterEntity,
    target_id: uuid.UUID,
    query: Annotated[UsageQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> UsagePage:
    return await list_usage(
        db,
        current,
        company_id,
        entity_type,
        target_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
