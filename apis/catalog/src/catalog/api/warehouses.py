"""Stock-location definitions and the company location configuration singleton."""

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
from catalog.api.units import Idempotency, command_receipt, no_query, signing_secret, unique_query
from catalog.models.warehouses import (
    CompanyWarehouseConfiguration,
    WarehouseOperationPolicyRevision,
)
from catalog.schemas.pricing import CommandOutput
from catalog.schemas.units import ExpectedVersion
from catalog.schemas.warehouses import (
    ActivityDefaultsInput,
    ConfigurationBootstrap,
    OperationFlagsInput,
    OperationPolicyInput,
    OperationPolicyPreview,
    OperationPolicyView,
    WarehouseConfigurationDetail,
    WarehouseCreate,
    WarehouseDetail,
    WarehouseListItem,
    WarehouseQuery,
    WarehouseUpdate,
)
from catalog.tasks import warehouse_operations as operations
from catalog.tasks import warehouses as tasks
from catalog.tasks.classification import list_rows, read
from catalog.tasks.pricing_commands import command

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/warehouses",
    response_model=Page[WarehouseListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_warehouse",
    dependencies=[Depends(unique_query)],
)
async def list_warehouse(
    company_id: uuid.UUID,
    query: Annotated[WarehouseQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        tasks.WAREHOUSE,
        query,
        signing_secret(request),
    )


@router.get(
    "/warehouse-configuration",
    response_model=WarehouseConfigurationDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_warehouse_configuration",
)
async def get_warehouse_configuration(
    company_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> WarehouseConfigurationDetail:
    no_query(request)
    return await tasks.configuration(db, current, company_id)


@router.post(
    "/warehouse-configuration/bootstrap",
    response_model=CommandOutput,
    status_code=201,
    operation_id="bootstrap_catalog_warehouse_configuration",
)
async def bootstrap_warehouse_configuration(
    company_id: uuid.UUID,
    body: ConfigurationBootstrap,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        CompanyWarehouseConfiguration,
        body,
        idempotency_key,
        tasks.bootstrap,
        models=tasks.LOCATION_MODELS,
    )
    return command_receipt(result)


@router.post(
    "/warehouse-configuration/defaults",
    response_model=CommandOutput,
    operation_id="set_catalog_warehouse_activity_defaults",
)
async def set_activity_defaults(
    company_id: uuid.UUID,
    body: ActivityDefaultsInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    """A typed reviewed action, not a PATCH of pointer columns: it changes where later
    operations resolve to, so it needs `warehouse.publish` like a policy revision does."""
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        CompanyWarehouseConfiguration,
        body,
        idempotency_key,
        operations.set_defaults,
        action="update",
        models=operations.POLICY_MODELS,
        work_type=operations.WarehouseWork,
        publish_permission="warehouse.publish",
    )
    return command_receipt(result)


@router.get(
    "/warehouses/{object_id}",
    response_model=WarehouseDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_warehouse",
)
async def get_warehouse(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, tasks.WAREHOUSE)


@router.post(
    "/warehouses",
    response_model=WarehouseDetail,
    response_model_exclude_unset=True,
    operation_id="create_catalog_warehouse",
    status_code=201,
)
async def create_warehouse(
    company_id: uuid.UUID,
    body: WarehouseCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, tasks.WAREHOUSE, body, idempotency_key, "create"
    )


@router.patch(
    "/warehouses/{object_id}",
    response_model=WarehouseDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_warehouse",
)
async def update_warehouse(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: WarehouseUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, tasks.WAREHOUSE, body, idempotency_key, "update", object_id
    )


@router.post(
    "/warehouses/{object_id}/activate",
    response_model=WarehouseDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_warehouse",
)
async def activate_warehouse(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, tasks.WAREHOUSE, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/warehouses/{object_id}/deactivate",
    response_model=WarehouseDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_warehouse",
)
async def deactivate_warehouse(
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
        tasks.WAREHOUSE,
        body,
        idempotency_key,
        "deactivate",
        object_id,
    )


@router.get(
    "/warehouses/{object_id}/operation-policy",
    response_model=OperationPolicyView,
    response_model_exclude_unset=True,
    operation_id="get_catalog_warehouse_operation_policy",
)
async def get_operation_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> OperationPolicyView:
    no_query(request)
    return await operations.policy_view(db, current, company_id, object_id)


@router.post(
    "/warehouses/{object_id}/operation-policy/preview",
    response_model=OperationPolicyPreview,
    operation_id="preview_catalog_warehouse_operation_policy",
)
async def preview_operation_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: OperationFlagsInput,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> OperationPolicyPreview:
    """POST because the proposal is a body, not because anything is written: a preview
    allocates no revision number and reserves nothing, so it needs no idempotency key."""
    no_query(request)
    return await operations.preview(db, current, company_id, object_id, body)


@router.post(
    "/warehouses/{object_id}/operation-policy/publish",
    response_model=CommandOutput,
    status_code=201,
    operation_id="publish_catalog_warehouse_operation_policy",
)
async def publish_operation_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: OperationPolicyInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        WarehouseOperationPolicyRevision,
        body,
        idempotency_key,
        operations.publish_policy,
        object_id=object_id,
        action="publish",
        models=operations.POLICY_MODELS,
        work_type=operations.WarehouseWork,
        publish_permission="warehouse.publish",
    )
    return command_receipt(result)
