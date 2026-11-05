"""Dedicated stock owner channel with exact delegated company enrollment.

A fixed Vouchers transport key authenticates the service, never a company. New
effects additionally require the real actor's signed company/financial authority.
Expired attempts can only reconcile/cancel their exact retained owner evidence.
"""

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.errors import (
    AuthenticationRequiredError,
    NotFoundError,
    ValidationFailedError,
)
from billing_platform.idempotency import canonical_json
from billing_platform.service_auth import service_request_bytes, service_response_bytes
from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from voucher_execution import ExecutionCommand
from voucher_execution.transport import command_digest, headers, verify

from accounting.models.voucher_execution import VoucherExecution
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.tasks.stock_execution import dispatch
from accounting.tasks.stock_source_client import StockSourceClient
from accounting.tasks.voucher_money_execution import authority

router = APIRouter()
KEY_ID = "stock.current"


async def authenticated(request: Request, operation: str) -> tuple[ExecutionCommand, bytes, bytes]:
    configured = request.app.state.settings.stock_execution_secret
    if configured is None or request.headers.get("x-execution-key-id") != KEY_ID:
        raise AuthenticationRequiredError("stock execution service authority is unavailable")
    if request.url.query:
        raise ValidationFailedError("stock execution does not accept query parameters")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 1_048_576:
            raise ValidationFailedError("stock execution exceeds its native protocol bound")
    framed = service_request_bytes(
        method=request.method, path=request.url.path, query="", body=bytes(raw)
    )
    secret = configured.get_secret_value().encode()
    verify(secret, KEY_ID, operation, framed, request.headers)
    try:
        body = ExecutionCommand.model_validate_json(bytes(raw))
    except ValueError as exc:
        raise ValidationFailedError("invalid stock execution contract") from exc
    if (
        body.protocol_version != 2
        or body.source_payload.get("stock") is None
        or command_digest(body) != body.request_hash
    ):
        raise AuthenticationRequiredError("stock owner requires its exact typed execution evidence")
    return body, secret, framed


def respond(secret: bytes, framed: bytes, operation: str, value: dict[str, object]) -> Response:
    body = canonical_json(value)
    return Response(
        body,
        media_type="application/json",
        headers=headers(
            secret,
            KEY_ID,
            operation + ".response",
            service_response_bytes(request_bytes=framed, response_body=body),
            response=True,
        )
        | {"Cache-Control": "no-store"},
    )


async def owns_retained(request: Request, command: ExecutionCommand) -> bool:
    with tenant_scope(command.tenant_id):
        async with request.app.state.session_factory() as db:
            receipt = await db.scalar(
                select(VoucherExecution).where(
                    VoucherExecution.company_id == command.company_id,
                    VoucherExecution.execution_id == command.execution_id,
                )
            )
            if (
                receipt
                and receipt.request_hash == command.request_hash
                and receipt.operation_id == command.operation_id
            ):
                return True
            intent = await db.scalar(
                select(VoucherMoneyIntent).where(
                    VoucherMoneyIntent.company_id == command.company_id,
                    VoucherMoneyIntent.execution_id == command.execution_id,
                )
            )
            return bool(intent and intent.request_hash == command.request_hash)


# The transport identity and current gateway actor/company proof are both required.
# There is no deployment-maintained tenant/company list to strand a new company.
@router.post("/internal/v1/stock-voucher-executions", include_in_schema=False)
async def stock_command(request: Request) -> Response:
    operation = "stock.execution.command"
    body, secret, framed = await authenticated(request, operation)
    if not await owns_retained(request, body):
        proving = body.model_copy(
            update={"purpose": "REVERSE" if body.reversal_of_execution_id else "POST"}
        )
        current = authority(
            proving, request.app.state.settings.actor_signing_secret.get_secret_value().encode()
        )
        current.actor.require_scope(
            "accounting.stock.reverse" if proving.purpose == "REVERSE" else "accounting.stock.post",
            target=ScopePath(company_id=body.company_id),
        )
    settings = request.app.state.settings
    source = (
        StockSourceClient(
            settings.stock_owner_url, settings.stock_owner_secret.get_secret_value().encode()
        )
        if settings.stock_owner_url and settings.stock_owner_secret
        else None
    )
    result = await dispatch(
        request.app.state.session_factory,
        body,
        secret=settings.actor_signing_secret.get_secret_value().encode(),
        client=request.app.state.stock_posting_client.for_command(body)
        if request.app.state.stock_posting_client is not None
        else None,
        source_client=source,
        # A goods Purchase bill (B24) also needs the invoice release.
        enabled=settings.voucher_stock_enabled
        and (body.source_payload.get("invoice") is None or settings.voucher_invoice_enabled),
    )
    return respond(secret, framed, operation, result.model_dump(mode="json"))


# Exact signed accepted command binding permits recovery after user proof expiry;
# neither an opaque execution UUID nor the service key alone exposes a receipt.
@router.post("/internal/v1/stock-voucher-executions/status", include_in_schema=False)
async def stock_status(request: Request) -> Response:
    operation = "stock.execution.status"
    body, secret, framed = await authenticated(request, operation)
    with tenant_scope(body.tenant_id):
        async with request.app.state.session_factory() as db:
            row = await db.scalar(
                select(VoucherExecution).where(
                    VoucherExecution.company_id == body.company_id,
                    VoucherExecution.execution_id == body.execution_id,
                    VoucherExecution.request_hash == body.request_hash,
                    VoucherExecution.operation_id == body.operation_id,
                )
            )
            if row is None:
                raise NotFoundError("stock execution outcome is not available")
            return respond(secret, framed, operation, row.result)
