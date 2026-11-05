"""Location grouping, dated membership and bin routes.

Bins are flat like brand series and manufacturer sites are: the parent location travels in
the body, where the command framework's idempotency payload already covers it.
"""

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
from catalog.api.classification import write
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, no_query, signing_secret, unique_query
from catalog.schemas.classification import GroupParentListItem, GroupParentQuery
from catalog.schemas.units import ExpectedVersion
from catalog.schemas.warehouse_groups import (
    BinCreate,
    BinDetail,
    BinListItem,
    BinQuery,
    BinUpdate,
    GroupMemberQuery,
    PrimaryGroupInput,
    WarehouseGroupAssignmentListItem,
    WarehouseGroupChildrenQuery,
    WarehouseGroupCreate,
    WarehouseGroupDetail,
    WarehouseGroupListItem,
    WarehouseGroupQuery,
    WarehouseGroupReparent,
    WarehouseGroupUpdate,
    WarehouseStructureContext,
)
from catalog.schemas.warehouses import WarehouseDetail, WarehouseListItem
from catalog.tasks import warehouse_groups as tasks
from catalog.tasks.classification import (
    list_children,
    list_edge_history,
    list_parent_history,
    list_rows,
    read,
)
from catalog.tasks.field_context import load_field_context
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import business_date
from catalog.tasks.warehouses import WAREHOUSE

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/warehouse-structure",
    response_model=WarehouseStructureContext,
    operation_id="get_catalog_warehouse_structure",
    dependencies=[Depends(unique_query)],
)
async def structure_context(
    company_id: uuid.UUID,
    resource: Literal["groups", "bins"],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> WarehouseStructureContext:
    if set(request.query_params) != {"resource"}:
        from billing_platform.errors import ValidationFailedError

        raise ValidationFailedError("unsupported warehouse structure query")
    context = await load_field_context(
        db,
        current,
        company_id,
        "catalog.warehouse_group" if resource == "groups" else "catalog.warehouse_bin",
    )
    state = await policy_state(db, current, company_id)
    return WarehouseStructureContext(
        company_id=company_id,
        timezone=context.company.timezone,
        business_date=business_date(context.company.timezone),
        policy_generation=state.generation if state else 1,
        source_version=context.source_version,
    )


@router.get(
    "/warehouses/{object_id}/group-history",
    response_model=Page[WarehouseGroupAssignmentListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_warehouse_group_history",
    dependencies=[Depends(unique_query)],
)
async def membership_history(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[GroupParentQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[WarehouseGroupAssignmentListItem]:
    await read(db, current, company_id, object_id, WAREHOUSE)
    edge = WAREHOUSE.membership
    assert edge is not None
    return await list_edge_history(
        db,
        current,
        company_id,
        object_id,
        query,
        signing_secret(request),
        edge,
        WarehouseGroupAssignmentListItem,
    )


@router.post(
    "/warehouse-groups",
    response_model=WarehouseGroupDetail,
    status_code=201,
    response_model_exclude_unset=True,
    operation_id="create_catalog_warehouse_group",
)
async def create_group(
    company_id: uuid.UUID,
    body: WarehouseGroupCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, tasks.WAREHOUSE_GROUP, body, idempotency_key, "create"
    )


@router.get(
    "/warehouse-groups",
    response_model=Page[WarehouseGroupListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_warehouse_groups",
    dependencies=[Depends(unique_query)],
)
async def list_groups(
    company_id: uuid.UUID,
    query: Annotated[WarehouseGroupQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db, current, company_id, tasks.WAREHOUSE_GROUP, query, signing_secret(request)
    )


@router.get(
    "/warehouse-groups/{object_id}",
    response_model=WarehouseGroupDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_warehouse_group",
)
async def get_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, tasks.WAREHOUSE_GROUP)


@router.patch(
    "/warehouse-groups/{object_id}",
    response_model=WarehouseGroupDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_warehouse_group",
)
async def update_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: WarehouseGroupUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        tasks.WAREHOUSE_GROUP,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/warehouse-groups/{object_id}/activate",
    response_model=WarehouseGroupDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_warehouse_group",
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
        request,
        current,
        company_id,
        tasks.WAREHOUSE_GROUP,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/warehouse-groups/{object_id}/deactivate",
    response_model=WarehouseGroupDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_warehouse_group",
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
        request,
        current,
        company_id,
        tasks.WAREHOUSE_GROUP,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )


@router.post(
    "/warehouse-groups/{object_id}/reparent",
    response_model=WarehouseGroupDetail,
    response_model_exclude_unset=True,
    operation_id="move_catalog_warehouse_group",
)
async def move_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: WarehouseGroupReparent,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        tasks.WAREHOUSE_GROUP,
        body,
        idempotency_key,
        "move",
        object_id,
    )


@router.get(
    "/warehouse-groups/{object_id}/parents",
    response_model=Page[GroupParentListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_warehouse_group_parent_history",
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
        db, current, company_id, object_id, query, signing_secret(request), tasks.WAREHOUSE_GROUP
    )


@router.get(
    "/warehouse-groups/{object_id}/children",
    response_model=Page[WarehouseGroupListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_warehouse_group_children",
    dependencies=[Depends(unique_query)],
)
async def group_children(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[WarehouseGroupChildrenQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_children(
        db, current, company_id, object_id, query, signing_secret(request), tasks.WAREHOUSE_GROUP
    )


@router.get(
    "/warehouse-groups/{object_id}/members",
    response_model=Page[WarehouseListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_warehouse_group_members",
    dependencies=[Depends(unique_query)],
)
async def group_members(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[GroupMemberQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    """The rollup, on a date. Locations the actor cannot read are absent, not summarized."""
    return await tasks.list_members(
        db, current, company_id, object_id, query, signing_secret(request)
    )


@router.put(
    "/warehouses/{object_id}/primary-group",
    response_model=WarehouseDetail,
    response_model_exclude_unset=True,
    operation_id="set_catalog_warehouse_primary_group",
)
async def set_primary_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: PrimaryGroupInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    """Appends a dated membership interval and closes the one in force. It grants nothing."""
    return await write(
        request, current, company_id, WAREHOUSE, body, idempotency_key, "assign", object_id
    )


@router.post(
    "/warehouse-bins",
    response_model=BinDetail,
    status_code=201,
    response_model_exclude_unset=True,
    operation_id="create_catalog_warehouse_bin",
)
async def create_bin(
    company_id: uuid.UUID,
    body: BinCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, tasks.WAREHOUSE_BIN, body, idempotency_key, "create"
    )


@router.get(
    "/warehouse-bins",
    response_model=Page[BinListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_warehouse_bins",
    dependencies=[Depends(unique_query)],
)
async def list_bins(
    company_id: uuid.UUID,
    query: Annotated[BinQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db, current, company_id, tasks.WAREHOUSE_BIN, query, signing_secret(request)
    )


@router.get(
    "/warehouse-bins/{object_id}",
    response_model=BinDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_warehouse_bin",
)
async def get_bin(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, tasks.WAREHOUSE_BIN)


@router.patch(
    "/warehouse-bins/{object_id}",
    response_model=BinDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_warehouse_bin",
)
async def update_bin(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: BinUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        tasks.WAREHOUSE_BIN,
        body,
        idempotency_key,
        "update",
        object_id,
    )


@router.post(
    "/warehouse-bins/{object_id}/activate",
    response_model=BinDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_warehouse_bin",
)
async def activate_bin(
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
        tasks.WAREHOUSE_BIN,
        body,
        idempotency_key,
        "activate",
        object_id,
    )


@router.post(
    "/warehouse-bins/{object_id}/deactivate",
    response_model=BinDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_warehouse_bin",
)
async def deactivate_bin(
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
        tasks.WAREHOUSE_BIN,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )
