"""Bounded signed owner inspection; this transport never enables stock execution."""

import asyncio
import datetime as dt

import httpx
from billing_platform.db.types import utcnow
from billing_platform.errors import PlatformError
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import request_headers, verify_response
from billing_platform.service_auth import service_request_bytes
from pydantic import Field, SecretStr, field_validator

from voucher_execution.contracts import Contract
from voucher_execution.stock_policy import (
    KEY,
    PATH,
    PolicyInspection,
    PolicyInspectionResult,
)
from voucher_execution.transport import validate_origin


class PolicyConnection(Contract):
    origin: str = Field(max_length=300)
    secret: SecretStr = Field(min_length=32, repr=False)

    @field_validator("origin")
    @classmethod
    def fixed_origin(cls, value: str) -> str:
        return validate_origin(value)


class PolicyUnavailableError(PlatformError):
    status_code = 503
    code = "stock_policy_unavailable"


class PolicyClient:
    def __init__(
        self,
        connection: PolicyConnection,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.connection, self.transport = connection, transport

    async def inspect(self, request: PolicyInspection) -> PolicyInspectionResult:
        raw = canonical_json(request.model_dump(mode="json"), maximum_bytes=262144)
        framed = service_request_bytes(method="POST", path=PATH, query="", body=raw)
        secret = self.connection.secret.get_secret_value().encode()
        try:
            async with (
                asyncio.timeout(4),
                httpx.AsyncClient(
                    timeout=3,
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as client,
            ):
                async with client.stream(
                    "POST",
                    self.connection.origin + PATH,
                    content=raw,
                    headers=request_headers(
                        requester="catalog",
                        owner="accounting",
                        key_id=KEY,
                        secret=secret,
                        framed=framed,
                    )
                    | {"Content-Type": "application/json"},
                ) as response:
                    data = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=4096):
                        data.extend(chunk)
                        if len(data) > 16384:
                            raise ValueError(
                                "policy inspection response exceeds its bound"
                            )
                    verify_response(
                        requester="catalog",
                        owner="accounting",
                        key_id=KEY,
                        secret=secret,
                        framed=framed,
                        body=bytes(data),
                        headers=response.headers,
                    )
                    if response.status_code != 200:
                        raise ValueError("policy owner did not accept this inspection")
                    result = PolicyInspectionResult.model_validate_json(bytes(data))
                    if (
                        result.check_id != request.check_id
                        or result.request_hash != request.digest()
                        or result.issued_at > utcnow() + dt.timedelta(seconds=5)
                        or result.expires_at <= utcnow() + dt.timedelta(seconds=5)
                    ):
                        raise ValueError(
                            "policy inspection binding or freshness differs"
                        )
                    return result
        except (httpx.HTTPError, ValueError, TimeoutError, PlatformError) as exc:
            raise PolicyUnavailableError(
                "native stock policy enforcement is unavailable"
            ) from exc
