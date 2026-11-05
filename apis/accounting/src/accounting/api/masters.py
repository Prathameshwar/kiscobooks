"""Explicit typed Accounting master routes. Generated from reviewed native resources."""

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
from accounting.schemas.master_opening import AccountCreation
from accounting.schemas.party_creation import (
    PartyCreation,
    PartyLedgerRepair,
    PartyLedgerRepairResult,
    PartyRoleActivation,
)
from accounting.schemas.query import AccountQuery, FieldSet, MasterQuery
from accounting.tasks.access import authorize
from accounting.tasks.commands import command, protected_read
from accounting.tasks.party_creation import (
    activate_party_role as activate_party_role_with_ledger,
)
from accounting.tasks.party_creation import create_party_with_details, repair_party_ledgers
from accounting.tasks.reads import field_set, listing

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422, 503)},
)


@router.get(
    "/account-heads",
    response_model=Page[l.AccountHeadListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account_head(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account_head"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountHeadListItem,
    )


@router.get("/account-heads/field-set", response_model=FieldSet)
async def fields_account_head(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account_head"])


@router.get(
    "/account-heads/{object_id}",
    response_model=s.AccountHeadDetail,
    response_model_exclude_unset=True,
)
async def get_account_head(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account_head"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.get(
    "/accounting-setup",
    response_model=Page[l.AccountingSetupListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_accounting_setup(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["accounting_setup"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountingSetupListItem,
    )


@router.get("/accounting-setup/field-set", response_model=FieldSet)
async def fields_accounting_setup(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["accounting_setup"])


@router.get(
    "/accounting-setup/{object_id}",
    response_model=s.AccountingSetupDetail,
    response_model_exclude_unset=True,
)
async def get_accounting_setup(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["accounting_setup"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.get(
    "/account-groups",
    response_model=Page[l.AccountGroupListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account_group(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account_group"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountGroupListItem,
    )


@router.get("/account-groups/field-set", response_model=FieldSet)
async def fields_account_group(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account_group"])


@router.get(
    "/account-groups/{object_id}",
    response_model=s.AccountGroupDetail,
    response_model_exclude_unset=True,
)
async def get_account_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account_group"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/account-groups",
    response_model=s.AccountGroupDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_account_group(
    company_id: uuid.UUID,
    body: s.AccountGroupCreate,
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
            BY_NAME["account_group"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/account-groups/{object_id}",
    response_model=s.AccountGroupDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_account_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.AccountGroupUpdate,
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
            BY_NAME["account_group"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/account-groups/{object_id}/activate",
    response_model=s.AccountGroupDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_account_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["account_group"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/account-groups/{object_id}/deactivate",
    response_model=s.AccountGroupDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_account_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["account_group"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/group-paths",
    response_model=Page[l.AccountGroupClosureListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account_group_closure(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account_group_closure"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountGroupClosureListItem,
    )


@router.get("/group-paths/field-set", response_model=FieldSet)
async def fields_account_group_closure(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account_group_closure"])


@router.get(
    "/group-paths/{object_id}",
    response_model=s.AccountGroupClosureDetail,
    response_model_exclude_unset=True,
)
async def get_account_group_closure(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account_group_closure"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.get(
    "/parties",
    response_model=Page[l.PartyListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyListItem,
    )


@router.get("/parties/field-set", response_model=FieldSet)
async def fields_party(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party"])


@router.get("/parties/{object_id}", response_model=s.PartyDetail, response_model_exclude_unset=True)
async def get_party(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/parties/create-with-details",
    response_model=s.PartyDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_ready_party(
    company_id: uuid.UUID,
    body: PartyCreation,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    receipt = await create_party_with_details(
        request.app.state.session_factory,
        current,
        body,
        idempotency_key,
        request.app.state.settings,
        posting_client=request.app.state.posting_client,
    )
    result = response(request, receipt)
    # The command is a collection action; its resource location is the party.
    result.headers["Location"] = f"../parties/{receipt.value.model_dump()['id']}"
    return result


@router.post("/parties/ledger-repair", response_model=PartyLedgerRepairResult, status_code=200)
async def repair_party_ledger(
    company_id: uuid.UUID,
    body: PartyLedgerRepair,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    """Give each active party role that has no account its account; report what cannot be."""
    no_query(request)
    return response(
        request,
        await repair_party_ledgers(
            request.app.state.session_factory,
            current,
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/parties/{object_id}",
    response_model=s.PartyDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyUpdate,
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
            BY_NAME["party"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/parties/{object_id}/activate",
    response_model=s.PartyDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_party(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/parties/{object_id}/deactivate",
    response_model=s.PartyDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_party(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-roles",
    response_model=Page[l.PartyRoleListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_role(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_role"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyRoleListItem,
    )


@router.get("/party-roles/field-set", response_model=FieldSet)
async def fields_party_role(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_role"])


@router.get(
    "/party-roles/{object_id}", response_model=s.PartyRoleDetail, response_model_exclude_unset=True
)
async def get_party_role(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_role"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-roles",
    response_model=s.PartyRoleDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_role(
    company_id: uuid.UUID,
    body: s.PartyRoleCreate,
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
            BY_NAME["party_role"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-roles/{object_id}",
    response_model=s.PartyRoleDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_role(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyRoleUpdate,
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
            BY_NAME["party_role"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-roles/{object_id}/activate",
    response_model=s.PartyRoleDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_party_role(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: PartyRoleActivation,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    """Activating a role also creates its account: no role is ever active without one."""
    no_query(request)
    return response(
        request,
        await activate_party_role_with_ledger(
            request.app.state.session_factory,
            current,
            object_id,
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.post(
    "/party-roles/{object_id}/deactivate",
    response_model=s.PartyRoleDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_party_role(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_role"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/payment-terms",
    response_model=Page[l.PaymentTermListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_payment_term(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["payment_term"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PaymentTermListItem,
    )


@router.get("/payment-terms/field-set", response_model=FieldSet)
async def fields_payment_term(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["payment_term"])


@router.get(
    "/payment-terms/{object_id}",
    response_model=s.PaymentTermDetail,
    response_model_exclude_unset=True,
)
async def get_payment_term(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["payment_term"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/payment-terms",
    response_model=s.PaymentTermDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_payment_term(
    company_id: uuid.UUID,
    body: s.PaymentTermCreate,
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
            BY_NAME["payment_term"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/payment-terms/{object_id}",
    response_model=s.PaymentTermDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_payment_term(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PaymentTermUpdate,
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
            BY_NAME["payment_term"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/payment-terms/{object_id}/activate",
    response_model=s.PaymentTermDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_payment_term(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["payment_term"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/payment-terms/{object_id}/deactivate",
    response_model=s.PaymentTermDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_payment_term(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["payment_term"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/payment-term-lines",
    response_model=Page[l.PaymentTermLineListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_payment_term_line(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["payment_term_line"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PaymentTermLineListItem,
    )


@router.get("/payment-term-lines/field-set", response_model=FieldSet)
async def fields_payment_term_line(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["payment_term_line"])


@router.get(
    "/payment-term-lines/{object_id}",
    response_model=s.PaymentTermLineDetail,
    response_model_exclude_unset=True,
)
async def get_payment_term_line(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["payment_term_line"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/payment-term-lines",
    response_model=s.PaymentTermLineDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_payment_term_line(
    company_id: uuid.UUID,
    body: s.PaymentTermLineCreate,
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
            BY_NAME["payment_term_line"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/payment-term-lines/{object_id}",
    response_model=s.PaymentTermLineDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_payment_term_line(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PaymentTermLineUpdate,
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
            BY_NAME["payment_term_line"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/accounts",
    response_model=Page[l.AccountListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[AccountQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountListItem,
    )


@router.get("/accounts/field-set", response_model=FieldSet)
async def fields_account(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account"])


@router.get(
    "/accounts/{object_id}", response_model=s.AccountDetail, response_model_exclude_unset=True
)
async def get_account(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/accounts", response_model=s.AccountDetail, response_model_exclude_unset=True, status_code=201
)
async def create_account(
    company_id: uuid.UUID,
    body: AccountCreation,
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
            BY_NAME["account"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
            posting_client=request.app.state.posting_client,
        ),
    )


@router.post(
    "/accounts/create-active",
    response_model=s.AccountDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_active_account(
    company_id: uuid.UUID,
    body: AccountCreation,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    """Create and activate an account in one transaction: create-then-activate, atomically."""
    no_query(request)
    receipt = await command(
        request.app.state.session_factory,
        current,
        BY_NAME["account"],
        "create_active",
        body,
        idempotency_key,
        request.app.state.settings,
        posting_client=request.app.state.posting_client,
    )
    result = response(request, receipt)
    # The command is a collection action; its resource location is the account.
    result.headers["Location"] = f"../accounts/{receipt.value.model_dump()['id']}"
    return result


@router.patch(
    "/accounts/{object_id}",
    response_model=s.AccountDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_account(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.AccountUpdate,
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
            BY_NAME["account"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/accounts/{object_id}/activate",
    response_model=s.AccountDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_account(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["account"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/accounts/{object_id}/deactivate",
    response_model=s.AccountDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_account(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["account"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/account-aliases",
    response_model=Page[l.AccountAliasListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account_alias(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account_alias"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountAliasListItem,
    )


@router.get("/account-aliases/field-set", response_model=FieldSet)
async def fields_account_alias(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account_alias"])


@router.get(
    "/account-aliases/{object_id}",
    response_model=s.AccountAliasDetail,
    response_model_exclude_unset=True,
)
async def get_account_alias(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account_alias"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/account-aliases",
    response_model=s.AccountAliasDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_account_alias(
    company_id: uuid.UUID,
    body: s.AccountAliasCreate,
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
            BY_NAME["account_alias"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/account-aliases/{object_id}",
    response_model=s.AccountAliasDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_account_alias(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.AccountAliasUpdate,
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
            BY_NAME["account_alias"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/account-aliases/{object_id}/activate",
    response_model=s.AccountAliasDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_account_alias(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["account_alias"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/account-aliases/{object_id}/deactivate",
    response_model=s.AccountAliasDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_account_alias(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["account_alias"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/account-group-aliases",
    response_model=Page[l.AccountGroupAliasListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account_group_alias(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account_group_alias"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountGroupAliasListItem,
    )


@router.get("/account-group-aliases/field-set", response_model=FieldSet)
async def fields_account_group_alias(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account_group_alias"])


@router.get(
    "/account-group-aliases/{object_id}",
    response_model=s.AccountGroupAliasDetail,
    response_model_exclude_unset=True,
)
async def get_account_group_alias(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account_group_alias"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/account-group-aliases",
    response_model=s.AccountGroupAliasDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_account_group_alias(
    company_id: uuid.UUID,
    body: s.AccountGroupAliasCreate,
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
            BY_NAME["account_group_alias"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/account-group-aliases/{object_id}",
    response_model=s.AccountGroupAliasDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_account_group_alias(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.AccountGroupAliasUpdate,
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
            BY_NAME["account_group_alias"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/account-group-aliases/{object_id}/activate",
    response_model=s.AccountGroupAliasDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_account_group_alias(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["account_group_alias"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/account-group-aliases/{object_id}/deactivate",
    response_model=s.AccountGroupAliasDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_account_group_alias(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["account_group_alias"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/account-external-keys",
    response_model=Page[l.AccountExternalKeyListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account_external_key(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account_external_key"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountExternalKeyListItem,
    )


@router.get("/account-external-keys/field-set", response_model=FieldSet)
async def fields_account_external_key(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account_external_key"])


@router.get(
    "/account-external-keys/{object_id}",
    response_model=s.AccountExternalKeyDetail,
    response_model_exclude_unset=True,
)
async def get_account_external_key(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account_external_key"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/account-external-keys",
    response_model=s.AccountExternalKeyDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_account_external_key(
    company_id: uuid.UUID,
    body: s.AccountExternalKeyCreate,
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
            BY_NAME["account_external_key"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/account-external-keys/{object_id}",
    response_model=s.AccountExternalKeyDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_account_external_key(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.AccountExternalKeyUpdate,
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
            BY_NAME["account_external_key"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/account-external-keys/{object_id}/activate",
    response_model=s.AccountExternalKeyDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_account_external_key(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["account_external_key"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/account-external-keys/{object_id}/deactivate",
    response_model=s.AccountExternalKeyDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_account_external_key(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["account_external_key"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-addresses",
    response_model=Page[l.PartyAddressListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_address(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_address"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyAddressListItem,
    )


@router.get("/party-addresses/field-set", response_model=FieldSet)
async def fields_party_address(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_address"])


@router.get(
    "/party-addresses/{object_id}",
    response_model=s.PartyAddressDetail,
    response_model_exclude_unset=True,
)
async def get_party_address(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_address"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-addresses",
    response_model=s.PartyAddressDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_address(
    company_id: uuid.UUID,
    body: s.PartyAddressCreate,
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
            BY_NAME["party_address"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-addresses/{object_id}",
    response_model=s.PartyAddressDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_address(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyAddressUpdate,
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
            BY_NAME["party_address"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-addresses/{object_id}/activate",
    response_model=s.PartyAddressDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_party_address(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_address"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-addresses/{object_id}/deactivate",
    response_model=s.PartyAddressDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_party_address(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_address"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-tax-registrations",
    response_model=Page[l.PartyTaxRegistrationListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_tax_registration(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_tax_registration"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyTaxRegistrationListItem,
    )


@router.get("/party-tax-registrations/field-set", response_model=FieldSet)
async def fields_party_tax_registration(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_tax_registration"])


@router.get(
    "/party-tax-registrations/{object_id}",
    response_model=s.PartyTaxRegistrationDetail,
    response_model_exclude_unset=True,
)
async def get_party_tax_registration(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_tax_registration"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-tax-registrations",
    response_model=s.PartyTaxRegistrationDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_tax_registration(
    company_id: uuid.UUID,
    body: s.PartyTaxRegistrationCreate,
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
            BY_NAME["party_tax_registration"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-tax-registrations/{object_id}",
    response_model=s.PartyTaxRegistrationDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_tax_registration(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyTaxRegistrationUpdate,
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
            BY_NAME["party_tax_registration"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-address-uses",
    response_model=Page[l.PartyAddressUseListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_address_use(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_address_use"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyAddressUseListItem,
    )


@router.get("/party-address-uses/field-set", response_model=FieldSet)
async def fields_party_address_use(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_address_use"])


@router.get(
    "/party-address-uses/{object_id}",
    response_model=s.PartyAddressUseDetail,
    response_model_exclude_unset=True,
)
async def get_party_address_use(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_address_use"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-address-uses",
    response_model=s.PartyAddressUseDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_address_use(
    company_id: uuid.UUID,
    body: s.PartyAddressUseCreate,
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
            BY_NAME["party_address_use"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-address-uses/{object_id}",
    response_model=s.PartyAddressUseDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_address_use(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyAddressUseUpdate,
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
            BY_NAME["party_address_use"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-address-uses/{object_id}/activate",
    response_model=s.PartyAddressUseDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_party_address_use(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_address_use"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-address-uses/{object_id}/deactivate",
    response_model=s.PartyAddressUseDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_party_address_use(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_address_use"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-contacts",
    response_model=Page[l.PartyContactListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_contact(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_contact"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyContactListItem,
    )


@router.get("/party-contacts/field-set", response_model=FieldSet)
async def fields_party_contact(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_contact"])


@router.get(
    "/party-contacts/{object_id}",
    response_model=s.PartyContactDetail,
    response_model_exclude_unset=True,
)
async def get_party_contact(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_contact"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-contacts",
    response_model=s.PartyContactDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_contact(
    company_id: uuid.UUID,
    body: s.PartyContactCreate,
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
            BY_NAME["party_contact"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-contacts/{object_id}",
    response_model=s.PartyContactDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_contact(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyContactUpdate,
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
            BY_NAME["party_contact"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-contacts/{object_id}/activate",
    response_model=s.PartyContactDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_party_contact(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_contact"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-contacts/{object_id}/deactivate",
    response_model=s.PartyContactDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_party_contact(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_contact"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-contact-uses",
    response_model=Page[l.PartyContactUseListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_contact_use(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_contact_use"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyContactUseListItem,
    )


@router.get("/party-contact-uses/field-set", response_model=FieldSet)
async def fields_party_contact_use(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_contact_use"])


@router.get(
    "/party-contact-uses/{object_id}",
    response_model=s.PartyContactUseDetail,
    response_model_exclude_unset=True,
)
async def get_party_contact_use(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_contact_use"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-contact-uses",
    response_model=s.PartyContactUseDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_contact_use(
    company_id: uuid.UUID,
    body: s.PartyContactUseCreate,
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
            BY_NAME["party_contact_use"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-contact-uses/{object_id}",
    response_model=s.PartyContactUseDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_contact_use(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyContactUseUpdate,
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
            BY_NAME["party_contact_use"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-contact-uses/{object_id}/activate",
    response_model=s.PartyContactUseDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_party_contact_use(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_contact_use"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-contact-uses/{object_id}/deactivate",
    response_model=s.PartyContactUseDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_party_contact_use(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_contact_use"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-identifiers",
    response_model=Page[l.PartyIdentifierListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_identifier(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_identifier"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyIdentifierListItem,
    )


@router.get("/party-identifiers/field-set", response_model=FieldSet)
async def fields_party_identifier(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_identifier"])


@router.get(
    "/party-identifiers/{object_id}",
    response_model=s.PartyIdentifierDetail,
    response_model_exclude_unset=True,
)
async def get_party_identifier(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_identifier"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-identifiers",
    response_model=s.PartyIdentifierDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_identifier(
    company_id: uuid.UUID,
    body: s.PartyIdentifierCreate,
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
            BY_NAME["party_identifier"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-identifiers/{object_id}",
    response_model=s.PartyIdentifierDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_identifier(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyIdentifierUpdate,
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
            BY_NAME["party_identifier"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-registration-addresses",
    response_model=Page[l.PartyRegistrationAddressListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_registration_address(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_registration_address"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyRegistrationAddressListItem,
    )


@router.get("/party-registration-addresses/field-set", response_model=FieldSet)
async def fields_party_registration_address(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_registration_address"])


@router.get(
    "/party-registration-addresses/{object_id}",
    response_model=s.PartyRegistrationAddressDetail,
    response_model_exclude_unset=True,
)
async def get_party_registration_address(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_registration_address"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-registration-addresses",
    response_model=s.PartyRegistrationAddressDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_registration_address(
    company_id: uuid.UUID,
    body: s.PartyRegistrationAddressCreate,
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
            BY_NAME["party_registration_address"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-registration-addresses/{object_id}",
    response_model=s.PartyRegistrationAddressDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_registration_address(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyRegistrationAddressUpdate,
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
            BY_NAME["party_registration_address"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-bank-accounts",
    response_model=Page[l.PartyBankAccountListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_bank_account(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_bank_account"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyBankAccountListItem,
    )


@router.get("/party-bank-accounts/field-set", response_model=FieldSet)
async def fields_party_bank_account(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_bank_account"])


@router.get(
    "/party-bank-accounts/{object_id}",
    response_model=s.PartyBankAccountDetail,
    response_model_exclude_unset=True,
)
async def get_party_bank_account(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_bank_account"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-bank-accounts",
    response_model=s.PartyBankAccountDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_bank_account(
    company_id: uuid.UUID,
    body: s.PartyBankAccountCreate,
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
            BY_NAME["party_bank_account"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-bank-accounts/{object_id}",
    response_model=s.PartyBankAccountDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_bank_account(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyBankAccountUpdate,
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
            BY_NAME["party_bank_account"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-bank-accounts/{object_id}/activate",
    response_model=s.PartyBankAccountDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_party_bank_account(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_bank_account"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-bank-accounts/{object_id}/deactivate",
    response_model=s.PartyBankAccountDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_party_bank_account(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_bank_account"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-commercial-types",
    response_model=Page[l.PartyCommercialTypeListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_commercial_type(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_commercial_type"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyCommercialTypeListItem,
    )


@router.get("/party-commercial-types/field-set", response_model=FieldSet)
async def fields_party_commercial_type(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_commercial_type"])


@router.get(
    "/party-commercial-types/{object_id}",
    response_model=s.PartyCommercialTypeDetail,
    response_model_exclude_unset=True,
)
async def get_party_commercial_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_commercial_type"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-commercial-types",
    response_model=s.PartyCommercialTypeDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_commercial_type(
    company_id: uuid.UUID,
    body: s.PartyCommercialTypeCreate,
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
            BY_NAME["party_commercial_type"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-commercial-types/{object_id}",
    response_model=s.PartyCommercialTypeDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_commercial_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyCommercialTypeUpdate,
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
            BY_NAME["party_commercial_type"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-commercial-types/{object_id}/activate",
    response_model=s.PartyCommercialTypeDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_party_commercial_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_commercial_type"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/party-commercial-types/{object_id}/deactivate",
    response_model=s.PartyCommercialTypeDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_party_commercial_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["party_commercial_type"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-commercial-type-memberships",
    response_model=Page[l.PartyCommercialTypeMembershipListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_commercial_type_membership(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_commercial_type_membership"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyCommercialTypeMembershipListItem,
    )


@router.get("/party-commercial-type-memberships/field-set", response_model=FieldSet)
async def fields_party_commercial_type_membership(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_commercial_type_membership"])


@router.get(
    "/party-commercial-type-memberships/{object_id}",
    response_model=s.PartyCommercialTypeMembershipDetail,
    response_model_exclude_unset=True,
)
async def get_party_commercial_type_membership(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_commercial_type_membership"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-commercial-type-memberships",
    response_model=s.PartyCommercialTypeMembershipDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_commercial_type_membership(
    company_id: uuid.UUID,
    body: s.PartyCommercialTypeMembershipCreate,
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
            BY_NAME["party_commercial_type_membership"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-commercial-type-memberships/{object_id}",
    response_model=s.PartyCommercialTypeMembershipDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_commercial_type_membership(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyCommercialTypeMembershipUpdate,
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
            BY_NAME["party_commercial_type_membership"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-accounting-policies",
    response_model=Page[l.PartyAccountingPolicyListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_accounting_policy(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_accounting_policy"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyAccountingPolicyListItem,
    )


@router.get("/party-accounting-policies/field-set", response_model=FieldSet)
async def fields_party_accounting_policy(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_accounting_policy"])


@router.get(
    "/party-accounting-policies/{object_id}",
    response_model=s.PartyAccountingPolicyDetail,
    response_model_exclude_unset=True,
)
async def get_party_accounting_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_accounting_policy"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-accounting-policies",
    response_model=s.PartyAccountingPolicyDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_accounting_policy(
    company_id: uuid.UUID,
    body: s.PartyAccountingPolicyCreate,
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
            BY_NAME["party_accounting_policy"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-accounting-policies/{object_id}",
    response_model=s.PartyAccountingPolicyDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_accounting_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyAccountingPolicyUpdate,
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
            BY_NAME["party_accounting_policy"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-credit-policies",
    response_model=Page[l.PartyCreditPolicyListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_credit_policy(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_credit_policy"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyCreditPolicyListItem,
    )


@router.get("/party-credit-policies/field-set", response_model=FieldSet)
async def fields_party_credit_policy(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_credit_policy"])


@router.get(
    "/party-credit-policies/{object_id}",
    response_model=s.PartyCreditPolicyDetail,
    response_model_exclude_unset=True,
)
async def get_party_credit_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_credit_policy"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-credit-policies",
    response_model=s.PartyCreditPolicyDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_credit_policy(
    company_id: uuid.UUID,
    body: s.PartyCreditPolicyCreate,
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
            BY_NAME["party_credit_policy"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-credit-policies/{object_id}",
    response_model=s.PartyCreditPolicyDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_credit_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyCreditPolicyUpdate,
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
            BY_NAME["party_credit_policy"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/account-tax-profiles",
    response_model=Page[l.AccountTaxProfileListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account_tax_profile(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account_tax_profile"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountTaxProfileListItem,
    )


@router.get("/account-tax-profiles/field-set", response_model=FieldSet)
async def fields_account_tax_profile(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account_tax_profile"])


@router.get(
    "/account-tax-profiles/{object_id}",
    response_model=s.AccountTaxProfileDetail,
    response_model_exclude_unset=True,
)
async def get_account_tax_profile(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account_tax_profile"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/account-tax-profiles",
    response_model=s.AccountTaxProfileDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_account_tax_profile(
    company_id: uuid.UUID,
    body: s.AccountTaxProfileCreate,
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
            BY_NAME["account_tax_profile"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/account-tax-profiles/{object_id}",
    response_model=s.AccountTaxProfileDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_account_tax_profile(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.AccountTaxProfileUpdate,
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
            BY_NAME["account_tax_profile"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/account-bank-profiles",
    response_model=Page[l.AccountBankProfileListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account_bank_profile(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account_bank_profile"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountBankProfileListItem,
    )


@router.get("/account-bank-profiles/field-set", response_model=FieldSet)
async def fields_account_bank_profile(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account_bank_profile"])


@router.get(
    "/account-bank-profiles/{object_id}",
    response_model=s.AccountBankProfileDetail,
    response_model_exclude_unset=True,
)
async def get_account_bank_profile(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account_bank_profile"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/account-bank-profiles",
    response_model=s.AccountBankProfileDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_account_bank_profile(
    company_id: uuid.UUID,
    body: s.AccountBankProfileCreate,
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
            BY_NAME["account_bank_profile"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/account-bank-profiles/{object_id}",
    response_model=s.AccountBankProfileDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_account_bank_profile(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.AccountBankProfileUpdate,
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
            BY_NAME["account_bank_profile"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/template-installations",
    response_model=Page[l.AccountTemplateInstallationListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account_template_installation(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account_template_installation"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountTemplateInstallationListItem,
    )


@router.get("/template-installations/field-set", response_model=FieldSet)
async def fields_account_template_installation(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account_template_installation"])


@router.get(
    "/template-installations/{object_id}",
    response_model=s.AccountTemplateInstallationDetail,
    response_model_exclude_unset=True,
)
async def get_account_template_installation(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account_template_installation"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.get(
    "/template-bindings",
    response_model=Page[l.AccountTemplateBindingListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account_template_binding(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account_template_binding"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountTemplateBindingListItem,
    )


@router.get("/template-bindings/field-set", response_model=FieldSet)
async def fields_account_template_binding(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account_template_binding"])


@router.get(
    "/template-bindings/{object_id}",
    response_model=s.AccountTemplateBindingDetail,
    response_model_exclude_unset=True,
)
async def get_account_template_binding(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account_template_binding"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.get(
    "/posting-mappings",
    response_model=Page[l.AccountPostingMappingListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account_posting_mapping(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account_posting_mapping"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountPostingMappingListItem,
    )


@router.get("/posting-mappings/field-set", response_model=FieldSet)
async def fields_account_posting_mapping(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account_posting_mapping"])


@router.get(
    "/posting-mappings/{object_id}",
    response_model=s.AccountPostingMappingDetail,
    response_model_exclude_unset=True,
)
async def get_account_posting_mapping(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account_posting_mapping"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/posting-mappings",
    response_model=s.AccountPostingMappingDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_account_posting_mapping(
    company_id: uuid.UUID,
    body: s.AccountPostingMappingCreate,
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
            BY_NAME["account_posting_mapping"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/posting-mappings/{object_id}",
    response_model=s.AccountPostingMappingDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_account_posting_mapping(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.AccountPostingMappingUpdate,
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
            BY_NAME["account_posting_mapping"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/account-tax-defaults",
    response_model=Page[l.AccountTaxDefaultListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_account_tax_default(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["account_tax_default"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.AccountTaxDefaultListItem,
    )


@router.get("/account-tax-defaults/field-set", response_model=FieldSet)
async def fields_account_tax_default(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["account_tax_default"])


@router.get(
    "/account-tax-defaults/{object_id}",
    response_model=s.AccountTaxDefaultDetail,
    response_model_exclude_unset=True,
)
async def get_account_tax_default(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["account_tax_default"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/account-tax-defaults",
    response_model=s.AccountTaxDefaultDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_account_tax_default(
    company_id: uuid.UUID,
    body: s.AccountTaxDefaultCreate,
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
            BY_NAME["account_tax_default"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/account-tax-defaults/{object_id}",
    response_model=s.AccountTaxDefaultDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_account_tax_default(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.AccountTaxDefaultUpdate,
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
            BY_NAME["account_tax_default"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/withholding-sections",
    response_model=Page[l.WithholdingSectionListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_withholding_section(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["withholding_section"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.WithholdingSectionListItem,
    )


@router.get("/withholding-sections/field-set", response_model=FieldSet)
async def fields_withholding_section(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["withholding_section"])


@router.get(
    "/withholding-sections/{object_id}",
    response_model=s.WithholdingSectionDetail,
    response_model_exclude_unset=True,
)
async def get_withholding_section(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["withholding_section"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/withholding-sections",
    response_model=s.WithholdingSectionDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_withholding_section(
    company_id: uuid.UUID,
    body: s.WithholdingSectionCreate,
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
            BY_NAME["withholding_section"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/withholding-sections/{object_id}",
    response_model=s.WithholdingSectionDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_withholding_section(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.WithholdingSectionUpdate,
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
            BY_NAME["withholding_section"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/withholding-sections/{object_id}/activate",
    response_model=s.WithholdingSectionDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def activate_withholding_section(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["withholding_section"],
            "activate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.post(
    "/withholding-sections/{object_id}/deactivate",
    response_model=s.WithholdingSectionDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def deactivate_withholding_section(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.ExpectedVersion,
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
            BY_NAME["withholding_section"],
            "deactivate",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/withholding-rates",
    response_model=Page[l.WithholdingRateListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_withholding_rate(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["withholding_rate"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.WithholdingRateListItem,
    )


@router.get("/withholding-rates/field-set", response_model=FieldSet)
async def fields_withholding_rate(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["withholding_rate"])


@router.get(
    "/withholding-rates/{object_id}",
    response_model=s.WithholdingRateDetail,
    response_model_exclude_unset=True,
)
async def get_withholding_rate(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["withholding_rate"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/withholding-rates",
    response_model=s.WithholdingRateDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_withholding_rate(
    company_id: uuid.UUID,
    body: s.WithholdingRateCreate,
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
            BY_NAME["withholding_rate"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/withholding-rates/{object_id}",
    response_model=s.WithholdingRateDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_withholding_rate(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.WithholdingRateUpdate,
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
            BY_NAME["withholding_rate"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/party-withholding-profiles",
    response_model=Page[l.PartyWithholdingProfileListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_party_withholding_profile(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["party_withholding_profile"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.PartyWithholdingProfileListItem,
    )


@router.get("/party-withholding-profiles/field-set", response_model=FieldSet)
async def fields_party_withholding_profile(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["party_withholding_profile"])


@router.get(
    "/party-withholding-profiles/{object_id}",
    response_model=s.PartyWithholdingProfileDetail,
    response_model_exclude_unset=True,
)
async def get_party_withholding_profile(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["party_withholding_profile"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/party-withholding-profiles",
    response_model=s.PartyWithholdingProfileDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_party_withholding_profile(
    company_id: uuid.UUID,
    body: s.PartyWithholdingProfileCreate,
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
            BY_NAME["party_withholding_profile"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/party-withholding-profiles/{object_id}",
    response_model=s.PartyWithholdingProfileDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_party_withholding_profile(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.PartyWithholdingProfileUpdate,
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
            BY_NAME["party_withholding_profile"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )


@router.get(
    "/withholding-certificates",
    response_model=Page[l.WithholdingCertificateListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def list_withholding_certificate(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BY_NAME["withholding_certificate"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        l.WithholdingCertificateListItem,
    )


@router.get("/withholding-certificates/field-set", response_model=FieldSet)
async def fields_withholding_certificate(
    company_id: uuid.UUID, request: Request, current: Access = Depends(access)
) -> FieldSet:
    no_query(request)
    return field_set(current, BY_NAME["withholding_certificate"])


@router.get(
    "/withholding-certificates/{object_id}",
    response_model=s.WithholdingCertificateDetail,
    response_model_exclude_unset=True,
)
async def get_withholding_certificate(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    spec = BY_NAME["withholding_certificate"]
    authorize(current, spec, "read")
    return protected_read(
        db, await company_object(db, spec.model, object_id, company_id=company_id), spec, current
    )


@router.post(
    "/withholding-certificates",
    response_model=s.WithholdingCertificateDetail,
    response_model_exclude_unset=True,
    status_code=201,
)
async def create_withholding_certificate(
    company_id: uuid.UUID,
    body: s.WithholdingCertificateCreate,
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
            BY_NAME["withholding_certificate"],
            "create",
            body,
            idempotency_key,
            request.app.state.settings,
        ),
    )


@router.patch(
    "/withholding-certificates/{object_id}",
    response_model=s.WithholdingCertificateDetail,
    response_model_exclude_unset=True,
    status_code=200,
)
async def update_withholding_certificate(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.WithholdingCertificateUpdate,
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
            BY_NAME["withholding_certificate"],
            "update",
            body,
            idempotency_key,
            request.app.state.settings,
            object_id,
        ),
    )
