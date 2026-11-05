"""Private service-authenticated commands and immutable reconciliation reads."""

import uuid

from billing_platform.db import tenant_scope
from billing_platform.errors import (
    AuthenticationRequiredError,
    NotFoundError,
    ValidationFailedError,
)
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import SnapshotCredential
from billing_platform.service_auth import service_request_bytes, service_response_bytes
from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from voucher_execution import ExecutionCommand
from voucher_execution.transport import headers, verify

from accounting.models.voucher_execution import VoucherExecution
from accounting.tasks.voucher_execution import execute

router = APIRouter()


@router.post("/internal/v1/voucher-invoice-previews", include_in_schema=False)
async def invoice_preview(request: Request) -> Response:
    """Service signature plus live user/owner field authority; no monetary effects."""
    from voucher_execution.invoice import InvoicePreviewCommand

    from accounting.api.auth import delegated_access
    from accounting.tasks.invoice_calculation import preview
    from accounting.tasks.invoice_goods import acquire as acquire_goods

    if (
        request.headers.get("x-execution-key-id", "")
        not in request.app.state.settings.voucher_execution_credentials
    ):
        raise AuthenticationRequiredError("execution authority unavailable")
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > 1048576:
            raise ValidationFailedError("invoice preview exceeds protocol limit")
        chunks.extend(chunk)
    raw = bytes(chunks)
    try:
        body = InvoicePreviewCommand.model_validate_json(raw)
    except ValueError as error:
        raise ValidationFailedError("invalid invoice preview contract") from error
    operation = "voucher.invoice.preview"
    credential, key_id, framed = authorize(request, body.tenant_id, body.company_id, operation, raw)
    current = delegated_access(
        body.authority,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        tenant_id=body.tenant_id,
        company_id=body.company_id,
        actor_user_id=body.actor_user_id,
    )
    # A goods bill's item facts come from Catalog before any Accounting session opens.
    goods = await acquire_goods(request.app.state.settings, body)
    with tenant_scope(body.tenant_id):
        async with request.app.state.session_factory() as db:
            result = await preview(db, current, body, goods=goods)
    return response(
        credential,
        key_id,
        framed,
        operation,
        canonical_json(result.model_dump(mode="json"), maximum_bytes=1048576),
    )


def authorize(
    request: Request, tenant: uuid.UUID, company: uuid.UUID, operation: str, body: bytes
) -> tuple[SnapshotCredential, str, bytes]:
    key_id = request.headers.get("x-execution-key-id", "")
    credential = request.app.state.settings.voucher_execution_credentials.get(key_id)
    if credential is None or not any(
        scope.tenant_id == tenant and scope.company_id == company for scope in credential.scopes
    ):
        raise AuthenticationRequiredError("execution company authority unavailable")
    if request.url.query or len(body) > 1048576:
        raise ValidationFailedError("unsupported execution request")
    framed = service_request_bytes(
        method=request.method, path=request.url.path, query="", body=body
    )
    verify(
        credential.secret.get_secret_value().encode(), key_id, operation, framed, request.headers
    )
    return credential, key_id, framed


def response(
    credential: SnapshotCredential, key_id: str, framed: bytes, operation: str, body: bytes
) -> Response:
    return Response(
        body,
        media_type="application/json",
        headers=headers(
            credential.secret.get_secret_value().encode(),
            key_id,
            operation + ".response",
            service_response_bytes(request_bytes=framed, response_body=body),
            response=True,
        )
        | {"Cache-Control": "no-store"},
    )


# Scoped service authentication above replaces user-route permissions on this private boundary.
@router.post("/internal/v1/voucher-executions", include_in_schema=False)
async def command(request: Request) -> Response:
    if (
        request.headers.get("x-execution-key-id", "")
        not in request.app.state.settings.voucher_execution_credentials
    ):
        raise AuthenticationRequiredError("execution authority unavailable")
    pieces = bytearray()
    async for chunk in request.stream():
        if len(pieces) + len(chunk) > 1048576:
            raise ValidationFailedError("execution body exceeds protocol limit")
        pieces.extend(chunk)
    raw = bytes(pieces)
    try:
        body = ExecutionCommand.model_validate_json(raw)
    except ValueError as error:
        raise ValidationFailedError("invalid execution contract") from error
    operation = "voucher.execution.command"
    credential, key_id, framed = authorize(request, body.tenant_id, body.company_id, operation, raw)
    if body.protocol_version == 2:
        from accounting.tasks.voucher_money_execution import dispatch

        result = await dispatch(
            request.app.state.session_factory,
            body,
            secret=request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
            client=request.app.state.posting_client,
            enabled=request.app.state.settings.voucher_money_enabled,
            invoices_enabled=request.app.state.settings.voucher_invoice_enabled,
        )
    else:
        with tenant_scope(body.tenant_id):
            async with request.app.state.session_factory() as db, db.begin():
                result = await execute(db, body)
    return response(
        credential, key_id, framed, operation, canonical_json(result.model_dump(mode="json"))
    )


@router.get(
    "/internal/v1/voucher-executions/{tenant_id}/{company_id}/{execution_id}",
    include_in_schema=False,
)
async def status(
    tenant_id: uuid.UUID, company_id: uuid.UUID, execution_id: uuid.UUID, request: Request
) -> Response:
    operation = "voucher.execution.status"
    credential, key_id, framed = authorize(
        request, tenant_id, company_id, operation, await request.body()
    )
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db:
            row = await db.scalar(
                select(VoucherExecution).where(
                    VoucherExecution.company_id == company_id,
                    VoucherExecution.execution_id == execution_id,
                )
            )
            if row is None:
                raise NotFoundError("execution outcome is not recorded")
            body = canonical_json(row.result)
    return response(credential, key_id, framed, operation, body)
