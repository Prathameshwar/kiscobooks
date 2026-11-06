"""Native stock reads and dated account configuration; effects use voucher execution."""

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.idempotency import has_retained_command
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.contracts import DelegatedAuthority

from accounting.api.auth import Access, access
from accounting.api.common import (
    ERROR_RESPONSES,
    Idempotency,
    no_query,
    response,
    session,
    unique_query,
)
from accounting.models.masters import AccountingSetup
from accounting.models.stock_count import StockCountObservation
from accounting.schemas import stock as s
from accounting.schemas.metadata import resolved_schema
from accounting.schemas.query import FieldDescription, FieldSet
from accounting.schemas.stock_count import CountDetail, CountObservationInput, CountScope
from accounting.schemas.stock_tracking import SerialListItem
from accounting.stock_resources import STOCK_POSITION
from accounting.tasks import stock_counts
from accounting.tasks.access import authorize
from accounting.tasks.reads import field_set
from accounting.tasks.stock_candidates import available_units, selection
from accounting.tasks.stock_openings import opening_lines
from accounting.tasks.stock_policy import correctable_policy, publish
from accounting.tasks.stock_reads import LISTS, SPECS, detail, listing, view
from accounting.tasks.stock_source_client import StockSourceClient, StockSourceUnavailableError

router = APIRouter(
    prefix="/v1/companies/{company_id}/stock",
    responses=ERROR_RESPONSES,
    dependencies=[Depends(unique_query)],
)
Resource = Literal["positions", "movements", "postings", "account-policies", "cost-pools"]


def selection_source(request: Request) -> tuple[DelegatedAuthority, StockSourceClient]:
    settings = request.app.state.settings
    if not settings.stock_owner_url or not settings.stock_owner_secret:
        raise StockSourceUnavailableError("stock selection source is not configured")
    proof = DelegatedAuthority(
        actor_context=request.headers["x-actor-context"],
        actor_signature=request.headers["x-actor-signature"],
        company_context=request.headers["x-company-context"],
        company_signature=request.headers["x-company-signature"],
    )
    return proof, StockSourceClient(
        settings.stock_owner_url, settings.stock_owner_secret.get_secret_value().encode()
    )


@router.post("/counts", response_model=CountDetail, status_code=201)
async def start_count(
    company_id: uuid.UUID,
    body: CountScope,
    key: Idempotency,
    request: Request,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    with tenant_scope(current.actor.tenant_id):
        factory = request.app.state.session_factory
        stock_counts.require_access(current, write=True)
        if await has_retained_command(factory, stock_counts.start_identity(current, body, key)):
            result = await stock_counts.create_local(factory, current, body, key, None)
        else:
            proof, source = selection_source(request)
            result = await stock_counts.create(factory, current, body, key, proof, source)
    return response(request, result)


@router.get("/counts/{count_id}", response_model=CountDetail)
async def read_count(
    company_id: uuid.UUID,
    count_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> CountDetail:
    no_query(request)
    stock_counts.require_access(current)
    original = await company_object(db, StockCountObservation, count_id, company_id=company_id)
    return await stock_counts.detail(
        db, current, await stock_counts.latest(db, current, original.root_id)
    )


@router.post("/counts/{count_id}/observations", response_model=CountDetail, status_code=201)
async def record_count(
    company_id: uuid.UUID,
    count_id: uuid.UUID,
    body: CountObservationInput,
    key: Idempotency,
    request: Request,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    with tenant_scope(current.actor.tenant_id):
        result = await stock_counts.observe(
            request.app.state.session_factory, current, count_id, body, key
        )
    return response(request, result)


@router.post("/selection", response_model=s.StockSelection)
async def stock_selection(
    company_id: uuid.UUID,
    body: s.StockSelectionInput,
    request: Request,
    current: Access = Depends(access),
) -> s.StockSelection:
    no_query(request)
    authorize(current, STOCK_POSITION, "read")
    proof, source = selection_source(request)
    with tenant_scope(current.actor.tenant_id):
        return await selection(
            request.app.state.session_factory,
            current,
            body,
            proof,
            source,
        )


@router.get(
    "/available-units", response_model=Page[SerialListItem], response_model_exclude_unset=True
)
async def stock_units(
    company_id: uuid.UUID,
    query: Annotated[s.StockAvailableUnitQuery, Query()],
    request: Request,
    current: Access = Depends(access),
) -> Page[SerialListItem]:
    authorize(current, STOCK_POSITION, "read")
    proof, source = selection_source(request)
    with tenant_scope(current.actor.tenant_id):
        return await available_units(
            request.app.state.session_factory,
            current,
            query,
            proof,
            source,
            request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        )


@router.get("/opening-lines", response_model=Page[s.StockOpeningLineListItem])
async def stock_opening_lines(
    company_id: uuid.UUID,
    query: Annotated[s.StockOpeningLineQuery, Query()],
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[s.StockOpeningLineListItem]:
    return await opening_lines(
        db,
        current,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get("/configuration", response_model=s.StockConfiguration)
async def configuration(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> s.StockConfiguration:
    no_query(request)
    authorize(current, STOCK_POSITION, "read")
    setup = await db.scalar(select(AccountingSetup).where(AccountingSetup.company_id == company_id))
    if setup is None:
        raise ConflictError("initialize Accounting for this company first")
    settings = request.app.state.settings
    return s.StockConfiguration(
        generation=setup.generation,
        posting_enabled=bool(
            settings.voucher_stock_enabled
            and settings.stock_execution_secret
            and settings.stock_owner_url
            and settings.stock_owner_secret
            and settings.stock_identity_url
            and settings.stock_identity_request_secret
            and settings.stock_identity_response_secret
        ),
        can_configure=not current.actor.impersonation_id
        and current.actor.allows_scope(
            "accounting.stock.configure", target=ScopePath(company_id=company_id)
        ),
        correctable_policy_id=await correctable_policy(db, company_id)
        if not current.actor.impersonation_id
        and current.actor.allows_scope(
            "accounting.stock.configure", target=ScopePath(company_id=company_id)
        )
        else None,
    )


@router.get("/positions/balance", response_model=s.StockPositionBalance)
async def position_balance(
    company_id: uuid.UUID,
    query: Annotated[s.StockPositionBalanceQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> s.StockPositionBalance:
    """Current company-owned stock physically in warehouses, summed in one indexed read."""
    statement, columns, allowed = view(current, STOCK_POSITION)
    required = {"item_id", "warehouse_id", "custody_kind", "quantity"}
    if not required.issubset(allowed):
        raise PermissionDeniedError("stock balance fields are not readable")
    statement = statement.where(
        columns["item_id"] == query.item_id,
        columns["custody_kind"] == "WAREHOUSE",
    )
    if query.warehouse_id is not None:
        statement = statement.where(columns["warehouse_id"] == query.warehouse_id)
    quantity = await db.scalar(
        statement.with_only_columns(
            func.coalesce(func.sum(columns["quantity"]), 0), maintain_column_froms=True
        )
    )
    return s.StockPositionBalance(
        item_id=query.item_id,
        warehouse_id=query.warehouse_id,
        quantity=quantity or Decimal("0.0000"),
    )


@router.get("/{resource}/field-set", response_model=FieldSet)
async def fields(
    company_id: uuid.UUID, resource: Resource, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    spec = SPECS[resource]
    result = field_set(current, spec)
    _, _, allowed = view(current, spec)
    known = {field.key for field in result.fields}
    definitions = resolved_schema(spec.detail)["properties"]
    return result.model_copy(
        update={
            "fields": [
                *(
                    field.model_copy(update={"readable": field.readable and field.key in allowed})
                    if field.key in spec.detail.model_fields
                    else field
                    for field in result.fields
                ),
                *(
                    FieldDescription(
                        key=key,
                        label=key.replace("_", " ").capitalize(),
                        required=False,
                        visible=True,
                        readable=key in allowed,
                        writable=False,
                        definition=definition,
                    )
                    for key, definition in definitions.items()
                    if key not in known
                ),
            ]
        }
    )


def register_reads(resource: str) -> None:
    # Each collection has one exact wire model. A union of structurally similar
    # sparse models can erase fields or reintroduce denied null-valued fields.
    async def records(
        company_id: uuid.UUID,
        query: Annotated[s.StockQuery, Query()],
        request: Request,
        current: Access = Depends(access),
        db: AsyncSession = Depends(session),
    ) -> Page[BaseModel]:
        return await listing(
            db,
            current,
            resource,
            query,
            request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        )

    async def record(
        company_id: uuid.UUID,
        object_id: uuid.UUID,
        request: Request,
        current: Access = Depends(access),
        db: AsyncSession = Depends(session),
    ) -> BaseModel:
        no_query(request)
        return await detail(db, current, resource, object_id)

    router.add_api_route(
        "/" + resource,
        records,
        methods=["GET"],
        response_model=Page.__class_getitem__(LISTS[resource]),
        response_model_exclude_unset=True,
        name="stock_" + resource.replace("-", "_"),
        operation_id="stock_list_" + resource.replace("-", "_"),
    )
    router.add_api_route(
        "/" + resource + "/{object_id}",
        record,
        methods=["GET"],
        response_model=SPECS[resource].detail,
        response_model_exclude_unset=True,
        name="stock_detail_" + resource.replace("-", "_"),
        operation_id="stock_detail_" + resource.replace("-", "_"),
    )


for _resource in SPECS:
    register_reads(_resource)


@router.post(
    "/account-policies",
    response_model=s.StockAccountPolicyDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def accounts(
    company_id: uuid.UUID,
    body: s.StockAccountPolicyCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request, await publish(request.app.state.session_factory, current, body, idempotency_key)
    )
