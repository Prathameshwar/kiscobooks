"""Reviewed, dated medicine classification on an existing item."""

import uuid
from typing import Annotated

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, command_receipt, no_query, unique_query
from catalog.models.products import Item
from catalog.models.regulatory import ItemRegulatoryClassification
from catalog.schemas.pricing import CommandOutput
from catalog.schemas.product_authoring import AdoptionQuery
from catalog.schemas.regulatory import (
    EffectiveRegulatoryClassification,
    RegulatoryClassificationInput,
)
from catalog.tasks import regulatory as tasks
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import command

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.post(
    "/items/{item_id}/regulatory-classifications",
    response_model=CommandOutput,
    operation_id="create_catalog_item_regulatory_classification",
)
async def classify(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    body: RegulatoryClassificationInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        ItemRegulatoryClassification,
        body,
        idempotency_key,
        tasks.classify,
        object_id=item_id,
        models=(ItemRegulatoryClassification,),
        work_type=tasks.RegulatoryWork,
        publish_permission="item.activate",
    )
    return command_receipt(result)


@router.get(
    "/items/{item_id}/regulatory-classification",
    response_model=EffectiveRegulatoryClassification | None,
    dependencies=[Depends(unique_query)],
    operation_id="get_catalog_item_regulatory_classification",
)
async def effective_classification(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    query: Annotated[AdoptionQuery, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> EffectiveRegulatoryClassification | None:
    access = ConfigurationAccess(db, current, company_id)
    await access.reference(Item, item_id)
    return await tasks.effective(access, item_id, query.as_of)
