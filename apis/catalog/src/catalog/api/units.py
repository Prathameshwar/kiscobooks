"""Unit and packaging APIs with the shared command and list contracts."""

import uuid
from typing import Annotated, Literal

from billing_platform.errors import ErrorEnvelope, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import CommandResult
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.config import Settings
from catalog.schemas.unit_defaults import UnitDefaultsInput, UnitDefaultsResult
from catalog.schemas.units import (
    ExpectedVersion,
    PackTypeDetail,
    PackTypeInput,
    PackTypeListItem,
    PackTypeListQuery,
    PackTypeUpdate,
    UnitCreate,
    UnitDetail,
    UnitListItem,
    UnitListQuery,
    UnitUpdate,
)
from catalog.tasks.unit_defaults import bootstrap_unit_defaults
from catalog.tasks.unit_masters import PACK, UNIT, Master, command, list_masters, read_master

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)
Idempotency = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


@router.post("/unit-defaults/bootstrap", response_model=UnitDefaultsResult)
async def bootstrap_defaults(
    company_id: uuid.UUID,
    body: UnitDefaultsInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    result = await bootstrap_unit_defaults(
        request.app.state.session_factory,
        current,
        company_id,
        idempotency_key,
        expected_inventory=body.expected_inventory,
    )
    return command_receipt(result)


def no_query(request: Request) -> None:
    if request.query_params:
        raise ValidationFailedError("this operation accepts no query parameters")


def unique_query(request: Request) -> None:
    if len(request.query_params.multi_items()) != len(request.query_params):
        raise ValidationFailedError("repeated query parameters are not supported")


async def write(
    request: Request,
    current: Actor,
    company_id: uuid.UUID,
    spec: Master,
    body: BaseModel,
    key: str,
    action: Literal["create", "update", "activate", "deactivate"],
    object_id: uuid.UUID | None = None,
) -> JSONResponse:
    no_query(request)
    result = await command(
        request.app.state.session_factory,
        current,
        company_id,
        spec,
        key=key,
        body=body,
        action=action,
        object_id=object_id,
    )
    return command_response(request, result, created=action == "create")


def signing_secret(request: Request) -> bytes:
    """The key the list cursors are signed with, read from settings rather than inlined."""
    settings: Settings = request.app.state.settings
    return settings.actor_signing_secret.get_secret_value().encode()


def receipt_headers(result: CommandResult[BaseModel]) -> dict[str, str]:
    """One definition of what a command answers with besides its body.

    A replay says so, and neither the first effect nor the replay is cacheable — a cached
    command response is a receipt for an effect the next reader never caused.
    """
    return {"Idempotency-Replayed": str(result.replayed).lower(), "Cache-Control": "no-store"}


def command_response(
    request: Request, result: CommandResult[BaseModel], *, created: bool
) -> JSONResponse:
    headers = receipt_headers(result)
    if created:
        headers["Location"] = request.url.path + "/" + str(result.value.model_dump()["id"])
    return JSONResponse(
        result.value.model_dump(mode="json", exclude_unset=True),
        status_code=result.status,
        headers=headers,
    )


def command_receipt(result: CommandResult[BaseModel]) -> JSONResponse:
    """A typed action's receipt, for commands whose output is already the whole answer.

    ``command_response`` is the master-CRUD form: it drops unset fields, because a detail
    model with a read-denied field must not answer with a null it does not actually know, and
    it addresses the row it created. A command receipt names an effect rather than a
    resource — every field is set, and there is no sub-resource to point at.
    """
    return JSONResponse(
        result.value.model_dump(mode="json"),
        status_code=result.status,
        headers=receipt_headers(result),
    )


@router.post(
    "/units",
    response_model=UnitDetail,
    status_code=201,
    response_model_exclude_unset=True,
    operation_id="create_catalog_unit",
)
async def create_unit(
    company_id: uuid.UUID,
    body: UnitCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, UNIT, body, idempotency_key, "create")


@router.get(
    "/units",
    response_model=Page[UnitListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_units",
    dependencies=[Depends(unique_query)],
)
async def list_units(
    company_id: uuid.UUID,
    query: Annotated[UnitListQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_masters(
        db,
        current,
        company_id,
        UNIT,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/units/{object_id}",
    response_model=UnitDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_unit",
)
async def get_unit(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read_master(db, current, company_id, object_id, UNIT)


@router.patch(
    "/units/{object_id}",
    response_model=UnitDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_unit",
)
async def update_unit(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: UnitUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, UNIT, body, idempotency_key, "update", object_id
    )


@router.post(
    "/units/{object_id}/activate",
    response_model=UnitDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_unit",
)
async def activate_unit(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, UNIT, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/units/{object_id}/deactivate",
    response_model=UnitDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_unit",
)
async def deactivate_unit(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, UNIT, body, idempotency_key, "deactivate", object_id
    )


@router.post(
    "/pack-types",
    response_model=PackTypeDetail,
    status_code=201,
    response_model_exclude_unset=True,
    operation_id="create_catalog_pack_type",
)
async def create_pack_type(
    company_id: uuid.UUID,
    body: PackTypeInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(request, current, company_id, PACK, body, idempotency_key, "create")


@router.get(
    "/pack-types",
    response_model=Page[PackTypeListItem],
    response_model_exclude_unset=True,
    operation_id="list_catalog_pack_types",
    dependencies=[Depends(unique_query)],
)
async def list_pack_types(
    company_id: uuid.UUID,
    query: Annotated[PackTypeListQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_masters(
        db,
        current,
        company_id,
        PACK,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/pack-types/{object_id}",
    response_model=PackTypeDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_pack_type",
)
async def get_pack_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read_master(db, current, company_id, object_id, PACK)


@router.patch(
    "/pack-types/{object_id}",
    response_model=PackTypeDetail,
    response_model_exclude_unset=True,
    operation_id="update_catalog_pack_type",
)
async def update_pack_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: PackTypeUpdate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, PACK, body, idempotency_key, "update", object_id
    )


@router.post(
    "/pack-types/{object_id}/activate",
    response_model=PackTypeDetail,
    response_model_exclude_unset=True,
    operation_id="activate_catalog_pack_type",
)
async def activate_pack_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, PACK, body, idempotency_key, "activate", object_id
    )


@router.post(
    "/pack-types/{object_id}/deactivate",
    response_model=PackTypeDetail,
    response_model_exclude_unset=True,
    operation_id="deactivate_catalog_pack_type",
)
async def deactivate_pack_type(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, PACK, body, idempotency_key, "deactivate", object_id
    )
