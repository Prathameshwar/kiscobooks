"""Signed Catalog definition lease acquisition outside Accounting transactions."""

from __future__ import annotations

import asyncio
import datetime as dt
import time
from typing import Any

import httpx
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    ErrorEnvelope,
    PermissionDeniedError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.idempotency import canonical_json
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from pydantic import ValidationError
from voucher_execution.stock_facts import StockFenceFacts, StockFenceRequest


class StockSourceUnavailableError(PlatformError):
    status_code = 503
    code = "stock_source_unavailable"


class StockSourceClient:
    def __init__(
        self, base_url: str, secret: bytes, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        url = httpx.URL(base_url)
        if (
            not url.host
            or url.path not in {"", "/"}
            or url.userinfo
            or url.query
            or url.fragment
            or (
                url.scheme != "https"
                and not (url.scheme == "http" and url.host in {"localhost", "127.0.0.1", "::1"})
            )
            or len(secret) < 32
        ):
            raise ValueError(
                "stock owner requires a fixed HTTPS or loopback origin and separate owner key"
            )
        self.base_url = base_url
        self.secret = secret
        self.transport = transport

    async def request(self, path: str, values: dict[str, Any], operation: str) -> bytes:
        body = canonical_json(values, maximum_bytes=262144)
        framed = service_request_bytes(method="POST", path=path, query="", body=body)
        stamp = int(time.time())
        key = ServiceKey("accounting", "catalog", frozenset({operation}), self.secret)
        headers = {
            "Content-Type": "application/json",
            "X-Source-Key-Id": "current",
            "X-Source-Issued-At": str(stamp),
            "X-Source-Signature": sign_service_body(
                key, key_id="current", operation=operation, timestamp=stamp, body=framed
            ),
        }
        response_operation = (
            "accounting.stock.fence.response"
            if operation.endswith("acquire")
            else "accounting.stock.fence.release.response"
        )
        try:
            async with (
                asyncio.timeout(8),
                httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=5,
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as client,
            ):
                async with client.stream("POST", path, content=body, headers=headers) as response:
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 1_048_576:
                            raise StockSourceUnavailableError(
                                "stock source evidence exceeds its native bound"
                            )
                    result = bytes(raw)
                    verify_service_body(
                        {
                            "current": ServiceKey(
                                "catalog",
                                "accounting",
                                frozenset({response_operation}),
                                self.secret,
                            )
                        },
                        key_id=response.headers.get("x-source-key-id", ""),
                        issuer="catalog",
                        audience="accounting",
                        operation=response_operation,
                        timestamp=response.headers.get("x-source-issued-at", ""),
                        signature=response.headers.get("x-source-signature", ""),
                        body=service_response_bytes(request_bytes=framed, response_body=result),
                        now=int(time.time()),
                        maximum_age=30,
                    )
                    if response.status_code != 200:
                        error = ErrorEnvelope.model_validate_json(result).error
                        if response.status_code == 403 and error.code == "permission_denied":
                            raise PermissionDeniedError(
                                "current stock source authority is not permitted"
                            )
                        if response.status_code in {401, 409} and error.code in {
                            "conflict",
                            "authentication_required",
                            "feature_not_enabled",
                        }:
                            raise ConflictError(
                                "stock source rules or authority changed; review a fresh execution"
                            )
                        if response.status_code == 422 and error.code == "validation_failed":
                            raise ValidationFailedError(
                                "native stock source rejected the captured references"
                            )
                        raise StockSourceUnavailableError(
                            "current stock source could not be verified"
                        )
                    return result
        except (ConflictError, PermissionDeniedError, ValidationFailedError):
            raise
        except (httpx.HTTPError, TimeoutError, ValueError, PlatformError) as exc:
            raise StockSourceUnavailableError(
                "stock source is unavailable; reconcile and retry this execution"
            ) from exc

    async def acquire(self, body: StockFenceRequest) -> StockFenceFacts:
        raw = await self.request(
            "/internal/v1/stock-source-fences",
            body.model_dump(mode="json"),
            "accounting.stock.fence.acquire",
        )
        try:
            facts = StockFenceFacts.model_validate_json(raw)
            if (
                any(
                    getattr(facts, name) != getattr(body, name)
                    for name in (
                        "tenant_id",
                        "company_id",
                        "execution_id",
                        "actor_user_id",
                        "stock_date",
                        "content_hash",
                        "purpose",
                        "action",
                    )
                )
                or facts.issued_at > utcnow() + dt.timedelta(seconds=5)
                or facts.expires_at > body.authority_expires_at
                or facts.expires_at <= utcnow() + dt.timedelta(seconds=15)
            ):
                raise ValueError("stock source binding or lifetime differs")
            if (
                {row.item_id for row in facts.items} != set(body.item_ids)
                or not set(body.warehouse_ids) <= {row.warehouse_id for row in facts.warehouses}
                or {row.bin_id for row in facts.bins} != set(body.bin_ids)
                or {unit.revision_id for item in facts.items for unit in item.opening_units}
                != set(body.opening_unit_revision_ids)
                or {unit.revision_id for item in facts.items for unit in item.quantity_units}
                != set(body.quantity_unit_revision_ids)
            ):
                raise ValueError("stock source references differ")
            extras = [row for row in facts.warehouses if row.warehouse_id not in body.warehouse_ids]
            if len(extras) > 1 or any(row.kind != "INTERNAL_TRANSIT" for row in extras):
                raise ValueError("stock source contains unexpected warehouse authority")
            return facts
        except (ValidationError, ValueError) as exc:
            raise StockSourceUnavailableError(
                "stock source evidence could not be verified"
            ) from exc

    async def release(self, facts: StockFenceFacts) -> None:
        if facts.purpose == "EXECUTION":
            try:
                async with asyncio.timeout(2):
                    await self.request(
                        "/internal/v1/stock-source-fences/release",
                        {
                            "tenant_id": str(facts.tenant_id),
                            "company_id": str(facts.company_id),
                            "execution_id": str(facts.execution_id),
                            "fence_id": str(facts.fence_id),
                        },
                        "accounting.stock.fence.release",
                    )
            except (TimeoutError, PlatformError) as exc:
                raise StockSourceUnavailableError(
                    "stock source release will expire safely"
                ) from exc
