"""Request-bound signed Design resolution; no browser chooses a template or canvas."""

import json
import time
import uuid
from typing import Any

import httpx
from billing_platform.errors import ConflictError
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)

from vouchers.schemas.printing import LayoutPreview, PrintLayoutOwner

OPERATION = "design.print.resolve"


async def resolve(
    owner: PrintLayoutOwner | None,
    tenant: uuid.UUID,
    company: uuid.UUID,
    type_id: uuid.UUID,
    currency: str,
    preview: LayoutPreview | None = None,
) -> dict[str, Any]:
    """The layout this bill prints on, or, for a preview, the one saved version asked for."""
    if owner is None or not any(
        scope.tenant_id == tenant and scope.company_id == company for scope in owner.scopes
    ):
        raise ConflictError("Purchase print layout authority is not configured")
    path = "/internal/v1/print-layout"
    body = json.dumps(
        {
            "tenant_id": str(tenant),
            "company_id": str(company),
            "voucher_kind": "PURCHASE",
            "voucher_type_id": str(type_id),
            "currency_code": currency,
        }
        | ({"preview": preview.model_dump(mode="json")} if preview is not None else {}),
        separators=(",", ":"),
    ).encode()
    framed = service_request_bytes(method="POST", path=path, query="", body=body)
    secret = owner.secret.get_secret_value().encode()
    key = ServiceKey("vouchers", "design", frozenset({OPERATION}), secret)
    stamp = int(time.time())
    try:
        async with httpx.AsyncClient(timeout=15) as transport:
            async with transport.stream(
                "POST",
                owner.origin + path,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Source-Key-Id": "current",
                    "X-Source-Issued-At": str(stamp),
                    "X-Source-Signature": sign_service_body(
                        key, key_id="current", operation=OPERATION, timestamp=stamp, body=framed
                    ),
                },
            ) as response:
                if preview is not None and response.status_code == 404:
                    raise ConflictError(
                        "this design version cannot be previewed for this company's Purchase "
                        "bills; save the design again or choose another version"
                    )
                response.raise_for_status()
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(chunks) + len(chunk) > 5_242_880:
                        raise ConflictError("Purchase print layout exceeds the supported size")
                    chunks.extend(chunk)
                raw = bytes(chunks)
                verify_service_body(
                    {"current": ServiceKey("design", "vouchers", frozenset({OPERATION}), secret)},
                    key_id=response.headers.get("x-source-key-id", ""),
                    issuer="design",
                    audience="vouchers",
                    operation=OPERATION,
                    timestamp=response.headers.get("x-source-issued-at", ""),
                    signature=response.headers.get("x-source-signature", ""),
                    body=service_response_bytes(request_bytes=framed, response_body=raw),
                    now=int(time.time()),
                    maximum_age=30,
                )
        result: dict[str, Any] = json.loads(raw)
        return result
    except (httpx.HTTPError, ValueError) as error:
        raise ConflictError("Purchase print layout service is unavailable") from error
