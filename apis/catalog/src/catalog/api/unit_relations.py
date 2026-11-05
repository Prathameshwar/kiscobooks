"""Declared canonical conversion and dated official-code endpoints."""

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
from catalog.api.units import Idempotency, command_response, no_query, unique_query
from catalog.schemas.units import (
    UnitConversionDetail,
    UnitConversionInput,
    UnitConversionListItem,
    UnitConversionQuery,
    UnitConvertInput,
    UnitConvertResult,
    UnitTaxCodeClose,
    UnitTaxCodeDetail,
    UnitTaxCodeInput,
    UnitTaxCodeListItem,
    UnitTaxCodeQuery,
)
from catalog.tasks.unit_relations import (
    CONVERSION,
    TAX_CODE,
    convert_units,
    list_relations,
    read_relation,
    relation_command,
)

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.post(
    "/unit-conversions",
    response_model=UnitConversionDetail,
    status_code=201,
    response_model_exclude_unset=True,
    operation_id="create_catalog_unit_conversion",
)
async def create_unit_conversion(
    company_id: uuid.UUID,
    body: UnitConversionInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await relation_command(
        request.app.state.session_factory, current, company_id, CONVERSION, body, idempotency_key
    )
    return command_response(request, result, created=True)


@router.get(
    "/unit-conversions",
    response_model=Page[UnitConversionListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_unit_conversions",
    dependencies=[Depends(unique_query)],
)
async def list_unit_conversions(
    company_id: uuid.UUID,
    query: Annotated[UnitConversionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_relations(
        db,
        current,
        company_id,
        CONVERSION,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/unit-conversions/{object_id}",
    response_model=UnitConversionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_unit_conversion",
)
async def get_unit_conversion(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read_relation(db, current, company_id, object_id, CONVERSION)


@router.post(
    "/unit-tax-codes",
    response_model=UnitTaxCodeDetail,
    status_code=201,
    response_model_exclude_unset=True,
    operation_id="create_catalog_unit_tax_code",
)
async def create_unit_tax_code(
    company_id: uuid.UUID,
    body: UnitTaxCodeInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await relation_command(
        request.app.state.session_factory, current, company_id, TAX_CODE, body, idempotency_key
    )
    return command_response(request, result, created=True)


@router.get(
    "/unit-tax-codes",
    response_model=Page[UnitTaxCodeListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_unit_tax_codes",
    dependencies=[Depends(unique_query)],
)
async def list_unit_tax_codes(
    company_id: uuid.UUID,
    query: Annotated[UnitTaxCodeQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_relations(
        db,
        current,
        company_id,
        TAX_CODE,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/unit-tax-codes/{object_id}",
    response_model=UnitTaxCodeDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_unit_tax_code",
)
async def get_unit_tax_code(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read_relation(db, current, company_id, object_id, TAX_CODE)


@router.post(
    "/unit-tax-codes/{object_id}/close",
    response_model=UnitTaxCodeDetail,
    response_model_exclude_unset=True,
    operation_id="close_catalog_unit_tax_code",
)
async def close_unit_tax_code(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: UnitTaxCodeClose,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await relation_command(
        request.app.state.session_factory,
        current,
        company_id,
        TAX_CODE,
        body,
        idempotency_key,
        object_id,
    )
    return command_response(request, result, created=False)


@router.post(
    "/units/convert", response_model=UnitConvertResult, operation_id="convert_catalog_units"
)
async def convert_quantity(
    company_id: uuid.UUID,
    body: UnitConvertInput,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> UnitConvertResult:
    no_query(request)
    return await convert_units(db, current, company_id, body)
