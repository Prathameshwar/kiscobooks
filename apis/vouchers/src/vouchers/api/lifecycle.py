"""Scoped administration lifecycle and permission-safe export."""

import datetime as dt
import uuid
from typing import Annotated, Any, Literal

from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import CommandReceipt
from billing_platform.pagination import CursorCodec
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, Idempotency, response, session, unique_query
from vouchers.models import core as m
from vouchers.schemas.configuration import Version
from vouchers.schemas.reads import ListQuery
from vouchers.tasks import administration, adoption, documents, reads
from vouchers.tasks.access import authorize, denied, fingerprint
from vouchers.tasks.common import audit, command, expected, get

router = APIRouter(
    prefix="/v1/companies/{company_id}", responses=ERRORS, dependencies=[Depends(unique_query)]
)


class CloseBinding(Version):
    valid_to: dt.date


def configuration_access(current: Access, mode: str = "read") -> None:
    if denied(current, "vouchers.configuration", {"policy", "status"}, mode):
        raise PermissionDeniedError("configuration fields are not accessible")


@router.get("/voucher-field-adoptions")
async def adoptions(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    authorize(current, "field.adopt")
    configuration_access(current)
    codec = CursorCodec(
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        context=f"adoptions:{fingerprint(current)}:{limit}",
    )
    statement = select(m.VoucherFieldAdoption).where(
        m.VoucherFieldAdoption.company_id == company_id
    )
    if cursor:
        try:
            last = uuid.UUID(codec.decode(cursor)["id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ValidationFailedError("invalid adoption cursor") from exc
        statement = statement.where(m.VoucherFieldAdoption.id > last)
    rows = list(await db.scalars(statement.order_by(m.VoucherFieldAdoption.id).limit(limit + 1)))
    return {
        "items": [
            {
                "id": str(row.id),
                "definition_id": str(row.definition_id),
                "source_version": row.source_version,
                "status": row.status,
                "row_version": row.row_version,
            }
            for row in rows[:limit]
        ],
        "page": {
            "limit": limit,
            "has_more": len(rows) > limit,
            "next_cursor": codec.encode({"id": str(rows[limit - 1].id)})
            if len(rows) > limit
            else None,
        },
    }


@router.post("/voucher-field-adoptions/{object_id}/apply")
async def apply_adoption(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: Version,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    configuration_access(current, "write")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await adoption.adopt(db, current, object_id, body.expected_version)
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        row = await get(db, current, m.VoucherFieldAdoption, uuid.UUID(refs["id"]))
        return {"id": str(row.id), "status": row.status, "row_version": row.row_version}

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "field.adopt",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=object_id,
        )
    )


@router.post("/{resource}/{object_id}/retire")
async def retire(
    company_id: uuid.UUID,
    resource: Literal[
        "voucher-types", "voucher-configurations", "voucher-series", "voucher-templates"
    ],
    object_id: uuid.UUID,
    body: Version,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    resources: dict[str, tuple[Any, str, str]] = {
        "voucher-types": (m.VoucherType, "type.manage", "type"),
        "voucher-configurations": (
            m.VoucherConfigurationProfile,
            "configuration.manage",
            "configuration",
        ),
        "voucher-series": (m.VoucherNumberSeries, "series.manage", "series"),
        "voucher-templates": (m.VoucherTemplate, "template.manage", "template"),
    }
    model, permission, entity = resources[resource]
    configuration_access(current, "write")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await get(db, current, model, object_id, lock=True)
        expected(row, body.expected_version)
        if row.status != "ACTIVE":
            raise ConflictError("resource is already retired")
        row.status = "RETIRED"
        row.row_version += 1
        audit(db, current, entity, row.id, "retire")
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await administration.detail(db, current, model, uuid.UUID(refs["id"]))

    return response(
        await command(
            request.app.state.session_factory,
            current,
            permission,
            idempotency_key,
            body,
            mutate,
            render,
            object_id=object_id,
        )
    )


@router.post("/voucher-configuration-bindings/{object_id}/close")
async def close_binding(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: CloseBinding,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    configuration_access(current, "write")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await get(db, current, m.VoucherConfigurationBinding, object_id, lock=True)
        expected(row, body.expected_version)
        if row.valid_to is not None or body.valid_to <= row.valid_from:
            raise ConflictError("binding cannot close at this date")
        row.valid_to = body.valid_to
        row.row_version += 1
        audit(db, current, "configuration", row.id, "binding_close")
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        row = await get(db, current, m.VoucherConfigurationBinding, uuid.UUID(refs["id"]))
        return {
            "id": str(row.id),
            "row_version": row.row_version,
            "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        }

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "configuration.manage",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=object_id,
        )
    )


@router.get("/voucher-export")
async def export(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[ListQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    authorize(current, "export")
    page = await reads.listing(
        db,
        current,
        m.Voucher,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
    return {
        "items": [await documents.detail(db, current, row["id"]) for row in page["items"]],
        "page": page["page"],
        "format": "voucher-current-revisions.v1",
    }


@router.get("/voucher-field-adoptions/{object_id}")
async def adoption_detail(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    authorize(current, "field.adopt")
    configuration_access(current)
    row = await get(db, current, m.VoucherFieldAdoption, object_id)
    projection = await get(db, current, m.VoucherDefinitionProjection, row.definition_id)
    if denied(current, projection.entity_type, {projection.field_key, "custom_fields"}, "read"):
        raise PermissionDeniedError("field definition is not readable")
    return {
        "id": str(row.id),
        "row_version": row.row_version,
        "status": row.status,
        "source_version": row.source_version,
        "current_definition": projection.definition,
        "proposed_definition": row.definition,
        "current_presentation": projection.presentation,
        "proposed_presentation": row.presentation,
    }


@router.post("/voucher-field-adoptions/{object_id}/preview")
async def preview_adoption(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: Version,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    from billing_platform.errors import PlatformError

    from vouchers.tasks.common import company_lock

    await adoption_detail(company_id, object_id, current, db)
    # Exercise the identical validator/claim/index path in a rollback-only savepoint.
    # Apply always revalidates against current documents; a preview never authorizes a later write.
    preview = await db.begin_nested()
    try:
        await company_lock(db, current)
        row = await adoption.adopt(db, current, object_id, body.expected_version)
        await db.flush()
        result: dict[str, Any] = {
            "can_apply": True,
            "source_version": row.source_version,
            "expected_version": body.expected_version,
        }
    except PlatformError as error:
        result = {"can_apply": False, "error_code": error.code, "message": error.message}
    finally:
        await preview.rollback()
    return result
