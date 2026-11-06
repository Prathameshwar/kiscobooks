"""Financial service HTTP adapter. Call before the money transaction or from its outbox worker."""

from __future__ import annotations

import datetime as dt
import time
import uuid
from collections.abc import Mapping
from typing import Any, Literal, Protocol

import httpx
from billing_platform.errors import AuthenticationRequiredError
from billing_platform.idempotency import canonical_json
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from pydantic import BaseModel, ConfigDict, Field


class ReservationError(Exception):
    """No posting authority was obtained. A caller must retain its durable operation ID."""


class ReservationRejectedError(ReservationError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"Identity rejected the reservation command ({status_code})")


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    company_id: uuid.UUID
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    settings: dict[str, Any]
    enabled_features: list[str]


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: uuid.UUID
    reservation_id: uuid.UUID
    status: Literal["pending", "confirmed", "aborted"]
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    features: list[str]
    confirmed_at: dt.datetime | None


class ReservationAuthority(Protocol):
    async def reserve(
        self,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        operation_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        configuration_hash: str,
        features: list[str],
    ) -> Receipt: ...


class PostingClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        key_id: str,
        request_secret: bytes,
        response_keys: Mapping[str, bytes],
        issuer: Literal["billing", "accounting"] = "billing",
    ) -> None:
        if (
            (
                http.base_url.scheme != "https"
                and not (
                    http.base_url.scheme == "http"
                    and http.base_url.host in {"127.0.0.1", "::1"}
                )
            )
            or not http.base_url.host
            or http.base_url.path not in {"", "/"}
        ):
            raise ValueError("Identity client requires HTTPS or a loopback HTTP origin")
        if http.base_url.query or http.base_url.fragment or http.base_url.userinfo:
            raise ValueError("Identity origin must not contain credentials or a query")
        if issuer not in {"billing", "accounting"}:
            raise ValueError("unsupported posting service")
        self.issuer = issuer
        self.http, self.key_id = http, key_id
        self.key = ServiceKey(
            issuer,
            "identity",
            frozenset(
                {
                    f"{issuer}.posting.configuration",
                    f"{issuer}.posting.reserve",
                    f"{issuer}.posting.confirmed",
                    f"{issuer}.posting.aborted",
                }
            ),
            request_secret,
        )
        self.response_keys = {
            name: ServiceKey(
                "identity", issuer, frozenset({"identity.posting.response"}), secret
            )
            for name, secret in response_keys.items()
        }
        if not 1 <= len(self.response_keys) <= 4:
            raise ValueError("one to four response keys are required")

    @staticmethod
    def _root(tenant_id: uuid.UUID, company_id: uuid.UUID) -> str:
        if not tenant_id.int or not company_id.int:
            raise ValueError("tenant and company must be nonzero identifiers")
        return f"/internal/v1/tenants/{tenant_id}/companies/{company_id}/posting"

    async def _request(
        self, path: str, operation: str, body: dict[str, Any] | None
    ) -> bytes:
        method = "GET" if body is None else "POST"
        raw = b"" if body is None else canonical_json(body)
        if len(raw) > 4096:
            raise ValueError("posting command exceeds its bound")
        framed = service_request_bytes(method=method, path=path, query="", body=raw)
        stamp = int(time.time())
        headers = {
            "x-source-issuer": self.issuer,
            "x-source-key-id": self.key_id,
            "x-source-issued-at": str(stamp),
            "x-source-signature": sign_service_body(
                self.key,
                key_id=self.key_id,
                operation=self.issuer + ".posting." + operation,
                timestamp=stamp,
                body=framed,
            ),
            "content-type": "application/json",
        }
        try:
            async with self.http.stream(
                method,
                path,
                content=raw,
                headers=headers,
                timeout=5,
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise ReservationRejectedError(response.status_code)
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise ReservationError("Identity response exceeds its bound")
                verify_service_body(
                    self.response_keys,
                    key_id=response.headers.get("x-source-key-id", ""),
                    issuer="identity",
                    audience=self.issuer,
                    operation="identity.posting.response",
                    timestamp=response.headers.get("x-source-issued-at", ""),
                    signature=response.headers.get("x-source-signature", ""),
                    body=service_response_bytes(
                        request_bytes=framed, response_body=bytes(data)
                    ),
                    now=int(time.time()),
                )
                return bytes(data)
        except (httpx.HTTPError, AuthenticationRequiredError) as exc:
            raise ReservationError(
                "Identity authorization could not be verified"
            ) from exc

    async def configuration(
        self, tenant_id: uuid.UUID, company_id: uuid.UUID
    ) -> Configuration:
        result = Configuration.model_validate_json(
            await self._request(
                self._root(tenant_id, company_id) + "/configuration",
                "configuration",
                None,
            )
        )
        if result.company_id != company_id:
            raise ReservationError("Identity returned a different company")
        return result

    async def reserve(
        self,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        operation_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        configuration_hash: str,
        features: list[str],
    ) -> Receipt:
        if not operation_id.int or not actor_user_id.int:
            raise ValueError("operation and actor identifiers must be nonzero")
        result = Receipt.model_validate_json(
            await self._request(
                self._root(tenant_id, company_id) + "/reservations",
                "reserve",
                {
                    "operation_id": str(operation_id),
                    "actor_user_id": str(actor_user_id),
                    "configuration_hash": configuration_hash,
                    "features": sorted(set(features)),
                },
            )
        )
        if (
            result.operation_id != operation_id
            or result.configuration_hash != configuration_hash
        ):
            raise ReservationError("Identity returned a different reservation")
        return result

    async def terminal(
        self,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        operation_id: uuid.UUID,
        outcome: Literal["confirmed", "aborted"],
        reference: str,
        posted_at: dt.datetime | None = None,
        intent: dict[str, Any] | None = None,
    ) -> Receipt:
        if outcome == "confirmed" and (posted_at is None or posted_at.tzinfo is None):
            raise ValueError("confirmation requires the actual aware posting timestamp")
        if intent is not None and outcome != "aborted":
            raise ValueError("only cancellation accepts a prepared intent")
        if outcome == "aborted" and posted_at is not None:
            raise ValueError("abort cannot have a posting timestamp")
        result = Receipt.model_validate_json(
            await self._request(
                self._root(tenant_id, company_id)
                + f"/reservations/{operation_id}/{outcome}",
                outcome,
                {
                    "terminal_reference": reference,
                    "posted_at": posted_at.isoformat() if posted_at else None,
                    **({"intent": intent} if intent is not None else {}),
                },
            )
        )
        if result.operation_id != operation_id or result.status != outcome:
            raise ReservationError("Identity returned a different terminal outcome")
        return result
