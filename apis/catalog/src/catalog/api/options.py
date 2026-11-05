"""Registered master pickers; target permissions and fields govern every query."""

import uuid
from typing import Annotated

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import unique_query
from catalog.schemas.options import OptionItem, OptionQuery
from catalog.tasks.options import list_options

router = APIRouter(
    prefix="/v1/companies/{company_id}/option-sources",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 422, 503)},
)


@router.get(
    "/{source_key}",
    response_model=Page[OptionItem],
    operation_id="list_catalog_options",
    dependencies=[Depends(unique_query)],
)
async def options(
    company_id: uuid.UUID,
    source_key: str,
    query: Annotated[OptionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[OptionItem]:
    return await list_options(
        db,
        current,
        company_id,
        source_key,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
