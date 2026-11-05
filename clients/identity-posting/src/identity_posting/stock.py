"""Stock-only first-use transport; ordinary financial company grants stay scoped."""

import datetime as dt
import time
import uuid
from typing import Literal, Self

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
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from identity_posting import Receipt, ReservationError, ReservationRejectedError

KEY_ID = "stock.current"
OPERATIONS = frozenset(
    {
        "accounting-stock.reserve",
        "accounting-stock.confirmed",
        "accounting-stock.aborted",
    }
)
FEATURES = frozenset(
    {"inventory", "batch_tracking", "serial_tracking", "expiry_tracking"}
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StockAuthority(Contract):
    actor_context: str = Field(min_length=1, max_length=32768, repr=False)
    actor_signature: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    company_context: str = Field(min_length=1, max_length=32768, repr=False)
    company_signature: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)


class StockReservationSource(Contract):
    execution_id: uuid.UUID
    command_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["POST", "REVERSE"]

    @field_validator("execution_id")
    @classmethod
    def real_execution(cls, value: uuid.UUID) -> uuid.UUID:
        if value.int == 0:
            raise ValueError("stock execution must identify a real accepted command")
        return value


class StockReservationIntent(Contract):
    operation_id: uuid.UUID
    actor_user_id: uuid.UUID
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    features: tuple[str, ...] = Field(min_length=1, max_length=4)
    source: StockReservationSource
    authority: StockAuthority = Field(repr=False)

    @field_validator("operation_id", "actor_user_id")
    @classmethod
    def real_identity(cls, value: uuid.UUID) -> uuid.UUID:
        if not value.int:
            raise ValueError(
                "stock reservation requires real operation and actor references"
            )
        return value

    @model_validator(mode="after")
    def only_stock_features(self) -> Self:
        if (
            "inventory" not in self.features
            or not set(self.features) <= FEATURES
            or len(set(self.features)) != len(self.features)
        ):
            raise ValueError("stock first use accepts distinct stock capabilities only")
        return self


class StockTerminalRequest(Contract):
    terminal_reference: str = Field(
        min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:/-]+$"
    )
    posted_at: dt.datetime | None = None
    intent: StockReservationIntent | None = None


class StockPostingClient:
    def __init__(
        self, http: httpx.AsyncClient, *, request_secret: bytes, response_secret: bytes
    ):
        origin = http.base_url
        if (
            (
                origin.scheme != "https"
                and not (
                    origin.scheme == "http" and origin.host in {"127.0.0.1", "::1"}
                )
            )
            or not origin.host
            or origin.path not in {"", "/"}
            or origin.userinfo
            or origin.query
            or origin.fragment
        ):
            raise ValueError("stock Identity connection requires a secure origin")
        if min(len(request_secret), len(response_secret)) < 32:
            raise ValueError("stock Identity credentials are incomplete")
        self.http = http
        self.request_key = ServiceKey(
            "accounting-stock", "identity", OPERATIONS, request_secret
        )
        self.response_key = ServiceKey(
            "identity",
            "accounting-stock",
            frozenset({"identity.stock-posting.response"}),
            response_secret,
        )

    @staticmethod
    def root(tenant: uuid.UUID, company: uuid.UUID) -> str:
        if not tenant.int or not company.int:
            raise ValueError("stock reservation requires real company scope")
        return f"/internal/v1/tenants/{tenant}/companies/{company}/stock-posting/reservations"

    async def request(self, path: str, operation: str, body: Contract) -> Receipt:
        raw = canonical_json(body.model_dump(mode="json"))
        if len(raw) > 131072:
            raise ReservationError("stock reservation exceeds its request bound")
        framed = service_request_bytes(method="POST", path=path, query="", body=raw)
        stamp = int(time.time())
        headers = {
            "x-source-key-id": KEY_ID,
            "x-source-issued-at": str(stamp),
            "x-source-signature": sign_service_body(
                self.request_key,
                key_id=KEY_ID,
                operation="accounting-stock." + operation,
                timestamp=stamp,
                body=framed,
            ),
            "content-type": "application/json",
        }
        try:
            async with self.http.stream(
                "POST",
                path,
                content=raw,
                headers=headers,
                timeout=5,
                follow_redirects=False,
            ) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise ReservationError(
                            "stock reservation response exceeds its bound"
                        )
                verify_service_body(
                    {KEY_ID: self.response_key},
                    key_id=response.headers.get("x-source-key-id", ""),
                    issuer="identity",
                    audience="accounting-stock",
                    operation="identity.stock-posting.response",
                    timestamp=response.headers.get("x-source-issued-at", ""),
                    signature=response.headers.get("x-source-signature", ""),
                    body=service_response_bytes(
                        request_bytes=framed, response_body=bytes(data)
                    ),
                    now=int(time.time()),
                )
                if response.status_code != 200:
                    raise ReservationRejectedError(response.status_code)
                return Receipt.model_validate_json(data)
        except (httpx.HTTPError, AuthenticationRequiredError, ValidationError) as exc:
            raise ReservationError(
                "stock Identity authorization could not be verified"
            ) from exc

    async def reserve(
        self, tenant: uuid.UUID, company: uuid.UUID, intent: StockReservationIntent
    ) -> Receipt:
        receipt = await self.request(self.root(tenant, company), "reserve", intent)
        if (
            receipt.operation_id != intent.operation_id
            or receipt.configuration_hash != intent.configuration_hash
            or not set(intent.features) <= set(receipt.features)
            or not set(receipt.features) <= FEATURES
        ):
            raise ReservationError("Identity returned a different stock reservation")
        return receipt

    async def terminal(
        self,
        tenant: uuid.UUID,
        company: uuid.UUID,
        operation_id: uuid.UUID,
        outcome: Literal["confirmed", "aborted"],
        body: StockTerminalRequest,
    ) -> Receipt:
        if (
            (
                outcome == "confirmed"
                and (
                    body.posted_at is None
                    or body.posted_at.tzinfo is None
                    or body.intent is not None
                )
            )
            or (outcome == "aborted" and body.posted_at is not None)
            or (body.intent is not None and body.intent.operation_id != operation_id)
        ):
            raise ValueError("stock terminal evidence differs from its outcome")
        receipt = await self.request(
            self.root(tenant, company) + f"/{operation_id}/{outcome}", outcome, body
        )
        if receipt.operation_id != operation_id or receipt.status != outcome:
            raise ReservationError(
                "Identity returned a different stock terminal outcome"
            )
        return receipt
