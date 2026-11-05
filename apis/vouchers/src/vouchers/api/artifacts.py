"""Protected artifact requests, asynchronous status and live-authority downloads."""

import uuid
from typing import Any

from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.idempotency import CommandReceipt
from billing_platform.pagination import CursorCodec
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, Idempotency, response, session
from vouchers.models import core as m
from vouchers.schemas.configuration import Version
from vouchers.schemas.documents import ArtifactCreate
from vouchers.schemas.reads import OperationDetail
from vouchers.tasks import artifacts
from vouchers.tasks.access import authorize, fingerprint
from vouchers.tasks.common import audit, command, expected, get

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERRORS)


@router.post("/vouchers/{voucher_id}/artifacts", status_code=202)
async def create_artifact(
    company_id: uuid.UUID,
    voucher_id: uuid.UUID,
    body: ArtifactCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await artifacts.prepare(
            db, current, voucher_id, body.expected_version, body.template_revision_id
        )
        await db.flush()
        return CommandReceipt(202, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        authorize(current, "read")
        row = await get(db, current, m.VoucherArtifact, uuid.UUID(refs["id"]))
        if row.permission_hash != fingerprint(current):
            raise PermissionDeniedError("artifact disclosure scope changed")
        return {"id": str(row.id), "status": row.status, "revision_id": str(row.revision_id)}

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "artifact.create",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=voucher_id,
        )
    )


def codec(request: Request, current: Access, artifact_id: uuid.UUID) -> CursorCodec:
    return CursorCodec(
        request.app.state.settings.artifact_signing_secret.get_secret_value().encode(),
        context=f"artifact:{artifact_id}:{fingerprint(current)}",
        ttl_seconds=120,
    )


@router.get("/voucher-artifacts/{artifact_id}")
async def artifact_status(
    company_id: uuid.UUID,
    artifact_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    authorize(current, "artifact.read")
    authorize(current, "read")
    row = await get(db, current, m.VoucherArtifact, artifact_id)
    if row.permission_hash != fingerprint(current):
        raise PermissionDeniedError("artifact disclosure scope changed")
    token = (
        codec(request, current, artifact_id).encode({"content_hash": row.content_hash})
        if row.status == "READY"
        else None
    )
    return {
        "id": str(row.id),
        "status": row.status,
        "revision_id": str(row.revision_id),
        "content_hash": row.content_hash,
        "download_token": token,
    }


@router.get("/voucher-artifacts/{artifact_id}/download")
async def download(
    company_id: uuid.UUID,
    artifact_id: uuid.UUID,
    token: str,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Response:
    authorize(current, "artifact.read")
    authorize(current, "read")
    row = await get(db, current, m.VoucherArtifact, artifact_id)
    if row.permission_hash != fingerprint(current):
        raise PermissionDeniedError("artifact disclosure scope changed")
    receipt = codec(request, current, artifact_id).decode(token)
    if row.status != "READY" or row.body is None or receipt.get("content_hash") != row.content_hash:
        raise ConflictError("artifact is not ready")
    return Response(
        row.body,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="voucher-{row.id}.html"',
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/voucher-operations/{operation_id}", response_model=OperationDetail)
async def operation_detail(
    company_id: uuid.UUID,
    operation_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> dict[str, Any]:
    authorize(current, "operation.read")
    row = await get(db, current, m.VoucherOperation, operation_id)
    return {
        "id": str(row.id),
        "voucher_id": str(row.voucher_id),
        "revision_id": str(row.revision_id),
        "status": row.status,
        "purpose": row.purpose,
        "attempt_count": row.attempt_count,
        "row_version": row.row_version,
        "rejection_code": (row.result or {}).get("rejection_code"),
    }


@router.get("/vouchers/{voucher_id}/history")
async def history(
    company_id: uuid.UUID,
    voucher_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    from billing_platform.errors import ValidationFailedError

    authorize(current, "history.read")
    await get(db, current, m.Voucher, voucher_id)
    if not 1 <= limit <= 200:
        raise ValidationFailedError("history limit must be between 1 and 200")
    statement = select(m.VoucherTransition).where(
        m.VoucherTransition.company_id == company_id, m.VoucherTransition.voucher_id == voucher_id
    )
    history_codec = CursorCodec(
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        context=f"history:{voucher_id}:{fingerprint(current)}:{limit}",
    )
    if cursor:
        try:
            after = uuid.UUID(history_codec.decode(cursor)["id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ValidationFailedError("invalid history cursor") from exc
        statement = statement.where(m.VoucherTransition.id > after)
    rows = list(await db.scalars(statement.order_by(m.VoucherTransition.id).limit(limit + 1)))
    # History exposes references and transitions, never retained custom values or comments.
    return {
        "items": [
            {
                "id": str(row.id),
                "revision_id": str(row.revision_id),
                "action": row.action,
                "from_status": row.from_status,
                "to_status": row.to_status,
                "voucher_version": row.voucher_version,
            }
            for row in rows[:limit]
        ],
        "page": {
            "limit": limit,
            "has_more": len(rows) > limit,
            "next_cursor": history_codec.encode({"id": str(rows[limit - 1].id)})
            if len(rows) > limit
            else None,
        },
    }


@router.post("/voucher-operations/{operation_id}/recover")
async def recover_operation(
    company_id: uuid.UUID,
    operation_id: uuid.UUID,
    body: Version,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await get(db, current, m.VoucherOperation, operation_id, lock=True)
        expected(row, body.expected_version)
        if row.purpose != "ARTIFACT" and (
            row.purpose not in {"POST", "REVERSE"} or row.command is None
        ):
            raise ConflictError("operation has no verified recovery adapter")
        if row.status != "PENDING":
            raise ConflictError("terminal operations cannot be re-executed")
        if row.purpose == "ARTIFACT":
            artifact = await get(db, current, m.VoucherArtifact, row.execution_id)
            if artifact.permission_hash != fingerprint(current):
                raise PermissionDeniedError("artifact disclosure scope changed")
        row.row_version += 1
        audit(db, current, "operation", row.id, "recover")
        # The restart-safe worker retries the original durable item; no new execution identity.
        return CommandReceipt(202, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        authorize(current, "operation.read")
        row = await get(db, current, m.VoucherOperation, uuid.UUID(refs["id"]))
        return {
            "id": str(row.id),
            "execution_id": str(row.execution_id),
            "status": row.status,
            "row_version": row.row_version,
        }

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "operation.recover",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=operation_id,
        )
    )


@router.post("/voucher-operations/{operation_id}/cancel")
async def cancel_execution(
    company_id: uuid.UUID,
    operation_id: uuid.UUID,
    body: Version,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await get(db, current, m.VoucherOperation, operation_id, lock=True)
        expected(row, body.expected_version)
        if row.purpose not in {"POST", "REVERSE"} or row.command is None or row.status != "PENDING":
            raise ConflictError("only pending owner executions can request cancellation")
        row.cancel_requested = True
        row.row_version += 1
        audit(db, current, "operation", row.id, "cancel_request")
        return CommandReceipt(202, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        authorize(current, "operation.read")
        row = await get(db, current, m.VoucherOperation, uuid.UUID(refs["id"]))
        return {
            "id": str(row.id),
            "status": row.status,
            "cancel_requested": row.cancel_requested,
            "row_version": row.row_version,
        }

    return response(
        await command(
            request.app.state.session_factory,
            current,
            "cancel",
            idempotency_key,
            body,
            mutate,
            render,
            object_id=operation_id,
        )
    )
