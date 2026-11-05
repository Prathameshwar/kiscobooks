"""Private Purchase files on a VM volume, with current authorization on every read."""

import asyncio
import uuid
from typing import Any
from urllib.parse import quote

from billing_platform.db import tenant_scope
from billing_platform.errors import PermissionDeniedError
from billing_platform.idempotency import CommandReceipt
from billing_platform.pagination import CursorCodec
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, Idempotency, response, session, unique_query
from vouchers.domain import supporting_files as disk
from vouchers.models.supporting_files import PurchaseSupportingFile
from vouchers.schemas.supporting_files import (
    SupportingFileDetail,
    SupportingFileRegistration,
    SupportingFileUpload,
)
from vouchers.tasks import supporting_files as files
from vouchers.tasks.access import fingerprint
from vouchers.tasks.common import audit, command, expected, get, values

router = APIRouter(
    prefix="/v1/companies/{company_id}/vouchers/{voucher_id}/supporting-files",
    responses=ERRORS,
    dependencies=[Depends(unique_query)],
)


def codec(
    request: Request, current: Access, file_id: uuid.UUID, revision_id: uuid.UUID
) -> CursorCodec:
    return CursorCodec(
        request.app.state.settings.artifact_signing_secret.get_secret_value().encode(),
        context=f"purchase-file:{file_id}:{revision_id}:{fingerprint(current)}",
        ttl_seconds=120,
    )


@router.post("", response_model=SupportingFileDetail, status_code=201)
async def upload(
    company_id: uuid.UUID,
    voucher_id: uuid.UUID,
    body: SupportingFileUpload,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    # Refuse permission, field, lifecycle and stale-version failures before decoding or
    # writing bytes. Disk I/O finishes outside the subsequent document transaction.
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            voucher, _, _ = await files.authority(db, current, voucher_id, editing=True)
            expected(voucher, body.expected_version)
    data, digest = await asyncio.to_thread(disk.decode, body.content_base64, body.media_type)
    key = disk.object_key(current.actor.tenant_id, company_id, voucher_id, digest)
    await asyncio.to_thread(
        disk.store, request.app.state.settings.supporting_file_root, key, data, digest
    )

    async def mutate(db: AsyncSession) -> CommandReceipt:
        voucher, _, _ = await files.authority(db, current, voucher_id, editing=True)
        expected(voucher, body.expected_version)
        row = await db.scalar(
            select(PurchaseSupportingFile).where(
                PurchaseSupportingFile.company_id == company_id,
                PurchaseSupportingFile.voucher_id == voucher_id,
                PurchaseSupportingFile.content_hash == digest,
            )
        )
        if row is None:
            row = PurchaseSupportingFile(
                **values(current),
                voucher_id=voucher_id,
                object_key=key,
                content_hash=digest,
                media_type=body.media_type,
                size_bytes=len(data),
                filename=body.filename,
            )
            db.add(row)
            await db.flush()
            audit(db, current, "supporting_file", row.id, "upload")
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        await files.authority(db, current, voucher_id)
        row = await get(db, current, PurchaseSupportingFile, uuid.UUID(refs["id"]))
        if row.voucher_id != voucher_id:
            raise PermissionDeniedError("supporting file belongs to another Purchase")
        return files.detail(row)

    identity = SupportingFileRegistration(
        expected_version=body.expected_version,
        filename=body.filename,
        media_type=body.media_type,
        content_hash=digest,
        size_bytes=len(data),
    )
    return response(
        await command(
            request.app.state.session_factory,
            current,
            "edit",
            idempotency_key,
            identity,
            mutate,
            render,
            object_id=voucher_id,
        )
    )


@router.get("", response_model=list[SupportingFileDetail])
async def listing(
    company_id: uuid.UUID,
    voucher_id: uuid.UUID,
    request: Request,
    revision_id: uuid.UUID | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> list[dict[str, Any]]:
    _, revision, raw = await files.authority(db, current, voucher_id, revision_id=revision_id)
    keys = [item["object_key"] for item in raw["attachments"]]
    if not keys:
        return []
    rows = await db.scalars(
        select(PurchaseSupportingFile)
        .where(
            PurchaseSupportingFile.company_id == company_id,
            PurchaseSupportingFile.voucher_id == voucher_id,
            PurchaseSupportingFile.object_key.in_(keys),
        )
        .order_by(PurchaseSupportingFile.id)
        .limit(20)
    )
    return [
        files.detail(
            row,
            token=codec(request, current, row.id, revision.id).encode({"hash": row.content_hash}),
        )
        for row in rows
    ]


@router.get("/{file_id}/download", response_class=Response)
async def download(
    company_id: uuid.UUID,
    voucher_id: uuid.UUID,
    file_id: uuid.UUID,
    token: str,
    request: Request,
    revision_id: uuid.UUID | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Response:
    row, revision = await files.linked(db, current, voucher_id, file_id, revision_id)
    receipt = codec(request, current, row.id, revision.id).decode(token)
    if receipt.get("hash") != row.content_hash:
        raise PermissionDeniedError("supporting-file download authority changed")
    data = await asyncio.to_thread(
        disk.read,
        request.app.state.settings.supporting_file_root,
        row.object_key,
        row.content_hash,
        row.size_bytes,
    )
    # As for the Purchase PDF: the access audit commits before any byte is disclosed.
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as audit_db, audit_db.begin():
            audit(
                audit_db,
                current,
                "supporting_file",
                row.id,
                "download",
                changes={"content_hash": row.content_hash, "size_bytes": row.size_bytes},
            )
    return Response(
        data,
        media_type=row.media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.filename, safe='')}",
        },
    )
