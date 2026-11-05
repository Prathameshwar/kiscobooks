"""Closed company-scoped metadata and reference routes for Accounting configuration."""

import uuid
from typing import Annotated

from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import ERROR_RESPONSES, session, unique_query
from accounting.schemas.configuration import (
    ConfigurationForm,
    ConfigurationResource,
    FormQuery,
    OptionQuery,
    OptionSource,
    ReferenceOption,
)

router = APIRouter(prefix="/v1/companies/{company_id}/configuration", responses=ERROR_RESPONSES)


async def form_access(resource: ConfigurationResource, current: Access = Depends(access)) -> Access:
    """Require resource authority before the shared session's company readiness gate."""
    from accounting.tasks.access import authorize
    from accounting.tasks.configuration import configuration_spec

    authorize(current, configuration_spec(resource), "read")
    return current


async def option_access(source: OptionSource, current: Access = Depends(access)) -> Access:
    from accounting.tasks.configuration_options import authorize_options

    authorize_options(current, source)
    return current


@router.get(
    "/{resource}/field-set",
    response_model=ConfigurationForm,
    dependencies=[Depends(unique_query)],
    operation_id="accounting_configuration_form",
)
async def configuration_form(
    company_id: uuid.UUID,
    resource: ConfigurationResource,
    query: Annotated[FormQuery, Query()],
    current: Access = Depends(form_access),
    db: AsyncSession = Depends(session),
) -> ConfigurationForm:
    from accounting.tasks.configuration import form

    return await form(db, current, resource, query)


@router.get(
    "/options/{source}",
    response_model=Page[ReferenceOption],
    dependencies=[Depends(unique_query)],
    operation_id="accounting_configuration_options",
)
async def configuration_options(
    company_id: uuid.UUID,
    source: OptionSource,
    query: Annotated[OptionQuery, Query()],
    request: Request,
    current: Access = Depends(option_access),
    db: AsyncSession = Depends(session),
) -> Page[ReferenceOption]:
    from accounting.tasks.configuration_options import options

    return await options(
        db,
        current,
        source,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
