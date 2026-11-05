"""Detached service-message authentication; separate from gateway actor grants.

Keys and allowed issuer/audience/operations are server configuration. The signed
bytes include the exact body, destination, operation and timestamp. Data inside a
message never grants its own publisher authority. Durable consumers additionally
use the inbox message identity for replay deduplication.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from billing_platform.errors import AuthenticationRequiredError

_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,119}\Z")


@dataclass(frozen=True, slots=True)
class ServiceKey:
    issuer: str
    audience: str
    operations: frozenset[str]
    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.issuer) or not _NAME.fullmatch(self.audience):
            raise ValueError("invalid service identity")
        if not self.operations or any(not _NAME.fullmatch(op) for op in self.operations):
            raise ValueError("explicit service operations required")
        if len(self.secret) < 32:
            raise ValueError("service key requires at least 32 bytes")


@dataclass(frozen=True, slots=True)
class ServicePrincipal:
    issuer: str
    audience: str
    operation: str
    key_id: str


def sign_service_body(
    key: ServiceKey,
    *,
    key_id: str,
    operation: str,
    timestamp: int,
    body: bytes,
) -> str:
    if not _NAME.fullmatch(key_id) or operation not in key.operations:
        raise ValueError("invalid key ID or service operation")
    if type(timestamp) is not int or timestamp < 0 or len(body) > 1_048_576:
        raise ValueError("invalid timestamp or oversized service body")
    header = f"v1\n{key_id}\n{key.issuer}\n{key.audience}\n{operation}\n{timestamp}\n"
    return hmac.new(key.secret, header.encode() + body, hashlib.sha256).hexdigest()


def verify_service_body(
    keys: Mapping[str, ServiceKey],
    *,
    key_id: str,
    issuer: str,
    audience: str,
    operation: str,
    timestamp: str,
    signature: str,
    body: bytes,
    now: int,
    maximum_age: int | None = 60,
) -> ServicePrincipal:
    if maximum_age is not None and (type(maximum_age) is not int or not 1 <= maximum_age <= 300):
        raise ValueError("invalid service authentication window")
    key = keys.get(key_id)
    valid = (
        _NAME.fullmatch(key_id) is not None
        and key is not None
        and key.issuer == issuer
        and key.audience == audience
        and operation in key.operations
        and re.fullmatch(r"[0-9]{1,12}", timestamp)
        and re.fullmatch(r"[0-9a-f]{64}", signature)
        and len(body) <= 1_048_576
    )
    if not valid or key is None:
        raise AuthenticationRequiredError("service authentication failed")
    issued = int(timestamp)
    if maximum_age is not None and abs(now - issued) > maximum_age:
        raise AuthenticationRequiredError("service authentication failed")
    expected = sign_service_body(
        key,
        key_id=key_id,
        operation=operation,
        timestamp=issued,
        body=body,
    )
    if not hmac.compare_digest(expected, signature):
        raise AuthenticationRequiredError("service authentication failed")
    return ServicePrincipal(issuer, audience, operation, key_id)


def service_request_bytes(*, method: str, path: str, query: str, body: bytes) -> bytes:
    """Bind HTTP service authentication to exact method/path/query and body bytes."""
    if (
        method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}
        or not path.startswith("/")
        or len(path) > 2048
        or len(query) > 4096
        or any(character in path + query for character in "\r\n")
        or len(body) > 1_048_576
    ):
        raise ValueError("invalid service HTTP request framing")
    return f"http-v1\n{method}\n{path}\n{query}\n{hashlib.sha256(body).hexdigest()}".encode()


def service_response_bytes(*, request_bytes: bytes, response_body: bytes) -> bytes:
    """A valid response for one snapshot request cannot be substituted for another."""
    if len(request_bytes) > 8192 or len(response_body) > 1_048_576:
        raise ValueError("invalid service HTTP response framing")
    return (
        f"response-v1\n{hashlib.sha256(request_bytes).hexdigest()}\n"
        f"{hashlib.sha256(response_body).hexdigest()}"
    ).encode()


class CompanyServiceScope(BaseModel):
    """Explicit tenant/company grant; authenticated services have no implicit scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant_id: uuid.UUID
    company_id: uuid.UUID

    @model_validator(mode="after")
    def real_scope(self) -> Self:
        if self.tenant_id.int == 0 or self.company_id.int == 0:
            raise ValueError("service scope must name real tenants and companies")
        return self
