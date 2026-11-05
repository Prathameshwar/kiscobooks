"""Bounded, request-bound transport for coordinated stock retirement only."""

import asyncio
import datetime as dt
import time
from collections.abc import AsyncIterable, Mapping
from typing import Any, Literal

import httpx
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
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
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from voucher_execution.stock_retirement import (
    RetirementEvidence,
    RetirementRelease,
    RetirementRequest,
)
from voucher_execution.transport import validate_origin

Owner = Literal["accounting", "vouchers"]
Action = Literal["inspect", "acquire", "release"]
KEY = "retirement.current"
PATH = "/internal/v1/stock-retirement"


async def bounded_body(stream: AsyncIterable[bytes]) -> bytes:
    data = bytearray()
    async for chunk in stream:
        data.extend(chunk)
        if len(data) > 131072:
            raise ValidationFailedError("retirement request exceeds its native bound")
    return bytes(data)


def response_body(
    secret: bytes, owner: Owner, action: Action, framed: bytes, value: dict[str, Any]
) -> tuple[bytes, dict[str, str]]:
    raw = canonical_json(value, maximum_bytes=16384)
    return raw, signing_headers(
        secret,
        owner,
        action,
        service_response_bytes(
            request_bytes=framed,
            response_body=raw,
        ),
        response=True,
    ) | {"Cache-Control": "no-store"}


class RetirementUnavailableError(PlatformError):
    status_code = 503
    code = "stock_retirement_unavailable"


class RetirementConnection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    origin: str = Field(max_length=300)
    secret: SecretStr = Field(min_length=32, repr=False)

    @field_validator("origin")
    @classmethod
    def fixed_origin(cls, value: str) -> str:
        return validate_origin(value)


def operation(owner: Owner, action: Action, *, response: bool = False) -> str:
    return f"stock.retirement.{owner}.{action}" + (".response" if response else "")


def signing_headers(
    secret: bytes, owner: Owner, action: Action, framed: bytes, *, response: bool = False
) -> dict[str, str]:
    purpose = operation(owner, action, response=response)
    key = ServiceKey(
        owner if response else "catalog",
        "catalog" if response else owner,
        frozenset({purpose}),
        secret,
    )
    timestamp = int(time.time())
    return {
        "X-Retirement-Key-Id": KEY,
        "X-Retirement-Issued-At": str(timestamp),
        "X-Retirement-Signature": sign_service_body(
            key,
            key_id=KEY,
            operation=purpose,
            timestamp=timestamp,
            body=framed,
        ),
    }


def verified(
    secret: bytes,
    owner: Owner,
    action: Action,
    framed: bytes,
    headers: Mapping[str, str],
    *,
    response: bool = False,
) -> None:
    purpose = operation(owner, action, response=response)
    issuer, audience = (owner, "catalog") if response else ("catalog", owner)
    values = {key.lower(): value for key, value in headers.items()}
    verify_service_body(
        {KEY: ServiceKey(issuer, audience, frozenset({purpose}), secret)},
        key_id=values.get("x-retirement-key-id", ""),
        issuer=issuer,
        audience=audience,
        operation=purpose,
        timestamp=values.get("x-retirement-issued-at", ""),
        signature=values.get("x-retirement-signature", ""),
        body=framed,
        now=int(time.time()),
        maximum_age=30,
    )


class RetirementClient:
    def __init__(
        self,
        owner: Owner,
        connection: RetirementConnection,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.owner, self.connection, self.transport = owner, connection, transport

    async def exchange(self, action: Action, values: dict[str, Any]) -> bytes:
        path = PATH + ("/release" if action == "release" else "")
        body = canonical_json(values, maximum_bytes=131072)
        framed = service_request_bytes(method="POST", path=path, query="", body=body)
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
                    self.connection.origin + path,
                    content=body,
                    headers=signing_headers(secret, self.owner, action, framed)
                    | {"Content-Type": "application/json"},
                ) as response:
                    data = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=16384):
                        data.extend(chunk)
                        if len(data) > 16384:
                            raise RetirementUnavailableError(
                                "retirement response exceeds its bound"
                            )
                    raw = bytes(data)
                    verified(
                        secret,
                        self.owner,
                        action,
                        service_response_bytes(
                            request_bytes=framed,
                            response_body=raw,
                        ),
                        response.headers,
                        response=True,
                    )
                    if response.status_code == 403:
                        raise PermissionDeniedError("current retirement authority is not permitted")
                    if response.status_code == 409:
                        raise ConflictError(
                            "retirement check changed; retry with current location details"
                        )
                    if response.status_code != 200:
                        raise RetirementUnavailableError(
                            "current retirement evidence is unavailable"
                        )
                    return raw
        except (PermissionDeniedError, ConflictError):
            raise
        except (httpx.HTTPError, ValueError, TimeoutError, PlatformError) as exc:
            raise RetirementUnavailableError(
                "current retirement evidence could not be verified"
            ) from exc

    async def check(self, request: RetirementRequest) -> RetirementEvidence:
        raw = await self.exchange(
            "inspect" if self.owner == "accounting" else "acquire", request.model_dump(mode="json")
        )
        try:
            result = RetirementEvidence.model_validate_json(raw)
            if (
                result.owner != self.owner
                or result.check_id != request.check_id
                or result.request_hash != request.digest()
            ):
                raise ValueError("retirement response differs from the requested scope")
            if (
                result.issued_at > utcnow() + dt.timedelta(seconds=5)
                or result.expires_at <= utcnow() + dt.timedelta(seconds=5)
            ):
                raise ValueError("retirement response has expired")
            return result
        except ValueError as exc:
            raise RetirementUnavailableError("retirement response could not be verified") from exc

    async def release(self, request: RetirementRelease) -> None:
        if self.owner != "vouchers":
            raise ValueError("only Vouchers has a retirement write lease")
        await self.exchange("release", request.model_dump(mode="json"))
