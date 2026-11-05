"""Signed effect-owner receipts; financial command producers remain capability-gated."""

import time
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.errors import AuthenticationRequiredError, ConflictError
from billing_platform.service_auth import ServiceKey, service_request_bytes, verify_service_body
from fastapi import APIRouter, Request

from vouchers.api.auth import limit_service_ingress
from vouchers.events.execution import ExecutionResult
from vouchers.tasks.operations import apply_result

router = APIRouter()


@router.post("/internal/v1/execution-results", include_in_schema=False)
async def receive_result(body: ExecutionResult, request: Request) -> dict[str, Any]:
    key_id = request.headers.get("x-service-key-id", "")
    credential = request.app.state.settings.source_credentials.get(key_id)
    if (
        credential is None
        or credential.issuer != "accounting"
        or "vouchers.execution.result" not in credential.operations
        or not any(
            scope.tenant_id == body.tenant_id and scope.company_id == body.company_id
            for scope in credential.scopes
        )
    ):
        raise AuthenticationRequiredError("effect owner scope is unavailable")
    operation = "vouchers.execution.result"
    verify_service_body(
        {
            key_id: ServiceKey(
                "accounting",
                "vouchers",
                frozenset({operation}),
                credential.secret.get_secret_value().encode(),
            )
        },
        key_id=key_id,
        issuer=request.headers.get("x-service-issuer", ""),
        audience="vouchers",
        operation=operation,
        timestamp=request.headers.get("x-service-timestamp", ""),
        signature=request.headers.get("x-service-signature", ""),
        body=service_request_bytes(
            method=request.method,
            path=request.url.path,
            query=request.url.query,
            body=await request.body(),
        ),
        now=int(time.time()),
    )
    limit_service_ingress(request, key_id, body.tenant_id, body.company_id)
    with tenant_scope(body.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            row = await apply_result(db, body)
            if row.purpose not in {"POST", "REVERSE"}:
                raise ConflictError("effect owner cannot complete a local document operation")
            return {"operation_id": str(row.id), "status": row.status}
