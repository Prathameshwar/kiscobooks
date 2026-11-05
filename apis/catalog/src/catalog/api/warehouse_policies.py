"""Per-product stock-location policies and replenishment bands.

Both writes are PUTs because both state the resource whole: the product's membership, or its
set of bands. A PATCH of one location would leave the reviewer approving a fragment, and an
omitted location could not mean both "keep" and "drop" (docs/catalog-warehouses.md §2).

They answer 200, not 201. Neither creates a resource the caller did not already name — the
product is the resource, and its policy is a property of it that these calls restate.
"""

import uuid

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, command_receipt, no_query
from catalog.models.warehouse_policies import ItemReplenishmentPolicy, ItemWarehousePolicy
from catalog.schemas.pricing import CommandOutput
from catalog.schemas.warehouse_policies import (
    ItemReplenishmentPolicyInput,
    ItemReplenishmentPolicyView,
    ItemWarehousePolicyInput,
    ItemWarehousePolicyView,
)
from catalog.tasks import warehouse_policies as tasks
from catalog.tasks.pricing_commands import command

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/items/{object_id}/warehouse-policy",
    response_model=ItemWarehousePolicyView,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item_warehouse_policy",
)
async def get_warehouse_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ItemWarehousePolicyView:
    """Answers for an unconfigured product too: the baseline is a documented answer, not a 404."""
    no_query(request)
    return await tasks.policy_view(db, current, company_id, object_id)


@router.put(
    "/items/{object_id}/warehouse-policy",
    response_model=CommandOutput,
    operation_id="set_catalog_item_warehouse_policy",
)
async def set_warehouse_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ItemWarehousePolicyInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        ItemWarehousePolicy,
        body,
        idempotency_key,
        tasks.set_policy,
        object_id=object_id,
        action="update",
        models=tasks.POLICY_MODELS,
        work_type=tasks.ItemPolicyWork,
        # No publish key: nothing here posts, numbers or moves money, and the location's own
        # reviewed policy remains the ceiling. The manage key is what this write costs.
        publish_permission="item_warehouse_policy.manage",
    )
    return command_receipt(result)


@router.get(
    "/items/{object_id}/replenishment-policy",
    response_model=ItemReplenishmentPolicyView,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item_replenishment_policy",
)
async def get_replenishment_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ItemReplenishmentPolicyView:
    no_query(request)
    return await tasks.replenishment_view(db, current, company_id, object_id)


@router.put(
    "/items/{object_id}/replenishment-policy",
    response_model=CommandOutput,
    operation_id="set_catalog_item_replenishment_policy",
)
async def set_replenishment_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ItemReplenishmentPolicyInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    """Bands, not quantities on hand. Catalog owns no stock and this write moves none."""
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        ItemReplenishmentPolicy,
        body,
        idempotency_key,
        tasks.set_replenishment,
        object_id=object_id,
        action="update",
        models=tasks.POLICY_MODELS,
        work_type=tasks.ItemReplenishmentWork,
        publish_permission="item_warehouse_policy.manage",
    )
    return command_receipt(result)
