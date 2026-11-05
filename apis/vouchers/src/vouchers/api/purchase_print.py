"""Current-authority print requests, safe status polling and expiring PDF downloads."""

import asyncio
import uuid
from typing import Annotated, Any, Literal, cast

from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.pagination import CursorCodec
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, Idempotency, response, session, unique_query
from vouchers.api.invoices import require_readable_inputs
from vouchers.domain.supporting_files import object_key, read
from vouchers.models import core as m
from vouchers.models.printing import VoucherPrintJob
from vouchers.schemas.printing import PrintCreate, PrintJobDetail
from vouchers.tasks import purchase_print
from vouchers.tasks.access import authorize
from vouchers.tasks.common import audit, command, get
from vouchers.tasks.documents import content
from vouchers.tasks.print_authority import fingerprint

router = APIRouter(
    prefix="/v1/companies/{company_id}", responses=ERRORS, dependencies=[Depends(unique_query)]
)


def codec(request: Request, current: Access, identity: uuid.UUID) -> CursorCodec:
    return CursorCodec(
        request.app.state.settings.artifact_signing_secret.get_secret_value().encode(),
        context=f"purchase-pdf:{identity}:{fingerprint(current)}",
        ttl_seconds=120,
    )


async def authorized(db: AsyncSession, current: Access, identity: uuid.UUID) -> VoucherPrintJob:
    authorize(current, "read")
    authorize(current, "artifact.read")
    job = await get(db, current, VoucherPrintJob, identity)
    if job.permission_hash != fingerprint(current):
        raise PermissionDeniedError("Purchase print disclosure scope changed; generate a new copy")
    voucher = await get(db, current, m.Voucher, job.voucher_id)
    if (
        voucher.row_version != job.snapshot["document"]["row_version"]
        or voucher.status != job.snapshot["document"]["status"]
    ):
        raise ConflictError(
            "Purchase changed since this print; generate a copy of the current revision"
        )
    revision = await get(db, current, m.VoucherRevision, job.revision_id)
    require_readable_inputs(current, await content(db, current, revision))
    return job


def presentation(request: Request, current: Access, job: VoucherPrintJob) -> dict[str, Any]:
    return PrintJobDetail(
        id=job.id,
        company_id=job.company_id,
        voucher_id=job.voucher_id,
        revision_id=job.revision_id,
        status=cast(Literal["PENDING", "RUNNING", "READY", "FAILED"], job.status),
        attempt=job.attempt,
        layout_name=job.snapshot["layout"]["name"],
        layout_version=job.snapshot["layout"]["version"],
        document_status=job.snapshot["document"]["status"],
        revision_number=job.snapshot["document"]["revision_number"],
        content_hash=job.content_hash,
        size_bytes=job.size_bytes,
        failure_code=job.failure_code,
        download_token=codec(request, current, job.id).encode({"content_hash": job.content_hash})
        if job.status == "READY"
        else None,
    ).model_dump(mode="json")


@router.post("/vouchers/{voucher_id}/print-jobs", response_model=PrintJobDetail, status_code=202)
async def create_print_job(
    company_id: uuid.UUID,
    voucher_id: uuid.UUID,
    body: PrintCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    snapshot = await purchase_print.prepare(request, current, voucher_id, body)

    async def mutate(db: AsyncSession) -> Any:
        return await purchase_print.admit(db, current, voucher_id, body, snapshot)

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return presentation(request, current, await authorized(db, current, uuid.UUID(refs["id"])))

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


@router.get("/voucher-print-jobs/{job_id}", response_model=PrintJobDetail)
async def print_status(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> JSONResponse:
    job = await authorized(db, current, job_id)
    return JSONResponse(presentation(request, current, job), headers={"Cache-Control": "no-store"})


@router.get(
    "/voucher-print-jobs/{job_id}/download",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def print_download(
    company_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    token: Annotated[str, Query(min_length=1, max_length=4096)],
    current: Access = Depends(access),
) -> Response:
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            job = await authorized(db, current, job_id)
            receipt = codec(request, current, job_id).decode(token)
            if (
                job.status != "READY"
                or job.content_hash is None
                or job.size_bytes is None
                or receipt.get("content_hash") != job.content_hash
            ):
                raise ConflictError("Purchase PDF is not ready")
            digest, size = job.content_hash, job.size_bytes
            snapshot, voucher_id = job.snapshot, job.voucher_id
        # Conditional owner policies may depend on records changed since generation.
        # No database transaction is held during the owner HTTP calls.
        await purchase_print.reauthorize(request, current, voucher_id, snapshot)
        async with request.app.state.session_factory() as db:
            await authorized(db, current, job_id)
    key = object_key(current.actor.tenant_id, company_id, voucher_id, digest)
    data = await asyncio.to_thread(
        read, request.app.state.settings.print_file_root, key, digest, size
    )
    # Disclosure is the access, not the ticket (every status poll carries one). The access audit
    # commits, in its own transaction through the outbox, after the integrity check and before any
    # byte is sent; if it cannot be written, nothing is disclosed. Hash and size are references.
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            audit(
                db,
                current,
                "print_job",
                job_id,
                "download",
                changes={"content_hash": digest, "size_bytes": size},
            )
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store, private",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="purchase-{voucher_id}.pdf"',
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
