"""Reviewed India party drug licences, scoped to an exact trading address."""

import uuid
from typing import Annotated

from billing_platform.db.access import company_object
from billing_platform.errors import ErrorEnvelope
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import Idempotency, no_query, response, session, unique_query
from accounting.resources import BY_NAME
from accounting.schemas import lists as l
from accounting.schemas import masters as s
from accounting.schemas.query import FieldSet, MasterQuery
from accounting.tasks.access import authorize
from accounting.tasks.commands import command, protected_read
from accounting.tasks.reads import field_set, listing

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422, 503)},
)
SPEC = BY_NAME["party_drug_licence"]


@router.get(
    "/party-drug-licences",
    response_model=Page[l.PartyDrugLicenceListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_licences(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        SPEC,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyDrugLicenceListItem,
    )


@router.get("/party-drug-licences/field-set", response_model=FieldSet)
async def licence_fields(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, SPEC)


@router.get(
    "/party-drug-licences/{object_id}",
    response_model=s.PartyDrugLicenceDetail,
    response_model_exclude_unset=True,
)
async def get_licence(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    authorize(current, SPEC, "read")
    return protected_read(
        db, await company_object(db, SPEC.model, object_id, company_id=company_id), SPEC, current
    )


@router.post(
    "/party-drug-licences",
    response_model=s.PartyDrugLicenceDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_licence(
    company_id: uuid.UUID,
    body: s.PartyDrugLicenceCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await command(
            request.app.state.session_factory,
            current,
            SPEC,
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-drug-licences/{object_id}",
    response_model=s.PartyDrugLicenceDetail,
    response_model_exclude_unset=True,
)
async def close_licence(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyDrugLicenceUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await command(
            request.app.state.session_factory,
            current,
            SPEC,
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )
