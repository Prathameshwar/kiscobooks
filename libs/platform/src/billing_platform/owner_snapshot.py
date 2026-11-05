"""Scoped owner snapshot transport; applications supply only their own selected facts."""

import time
import uuid
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, model_validator

from billing_platform.errors import AuthenticationRequiredError
from billing_platform.service_auth import (
    CompanyServiceScope,
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)


class SnapshotCredential(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    secret: SecretStr = Field(min_length=32)
    scopes: tuple[CompanyServiceScope, ...] = Field(default=(), max_length=1000)
    allow_enrolled_companies: StrictBool = False

    @model_validator(mode="after")
    def explicit_authority(self) -> "SnapshotCredential":
        if not self.scopes and not self.allow_enrolled_companies:
            raise ValueError("explicit scopes or enrolled-company capability are required")
        return self


def authorize_snapshot(
    credentials: Mapping[str, SnapshotCredential],
    *,
    owner: str,
    requester: str = "vouchers",
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    headers: Mapping[str, str],
    method: str,
    path: str,
    query: str,
    body: bytes,
    enrolled: bool = False,
) -> tuple[SnapshotCredential, bytes, str]:
    credential, framed, key_id = authenticate_snapshot(
        credentials,
        owner=owner,
        requester=requester,
        headers=headers,
        method=method,
        path=path,
        query=query,
        body=body,
    )
    require_snapshot_scope(
        credential, tenant_id=tenant_id, company_id=company_id, enrolled=enrolled
    )
    return credential, framed, key_id


def require_snapshot_scope(
    credential: SnapshotCredential,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    enrolled: bool = False,
) -> None:
    if not (
        (credential.allow_enrolled_companies and enrolled)
        or any(
            scope.tenant_id == tenant_id and scope.company_id == company_id
            for scope in credential.scopes
        )
    ):
        raise AuthenticationRequiredError("owner snapshot scope is unavailable")


def authenticate_snapshot(
    credentials: Mapping[str, SnapshotCredential],
    *,
    owner: str,
    requester: str = "vouchers",
    headers: Mapping[str, str],
    method: str,
    path: str,
    query: str,
    body: bytes,
) -> tuple[SnapshotCredential, bytes, str]:
    """Authenticate before any native enrollment lookup; this alone grants no company."""
    key_id = headers.get("x-source-key-id", "")
    credential = credentials.get(key_id)
    if credential is None:
        raise AuthenticationRequiredError("owner snapshot scope is unavailable")
    framed = service_request_bytes(method=method, path=path, query=query, body=body)
    key = ServiceKey(
        requester,
        owner,
        frozenset({f"{requester}.snapshot.read"}),
        credential.secret.get_secret_value().encode(),
    )
    verify_service_body(
        {key_id: key},
        key_id=key_id,
        issuer=requester,
        audience=owner,
        operation=f"{requester}.snapshot.read",
        timestamp=headers.get("x-source-issued-at", ""),
        signature=headers.get("x-source-signature", ""),
        body=framed,
        now=int(time.time()),
    )
    return credential, framed, key_id


def response_headers(
    credential: SnapshotCredential,
    *,
    owner: str,
    key_id: str,
    request_bytes: bytes,
    body: bytes,
    requester: str = "vouchers",
) -> dict[str, str]:
    timestamp = int(time.time())
    key = ServiceKey(
        owner,
        requester,
        frozenset({f"{requester}.snapshot.response"}),
        credential.secret.get_secret_value().encode(),
    )
    return {
        "X-Source-Key-Id": key_id,
        "X-Source-Issued-At": str(timestamp),
        "X-Source-Signature": sign_service_body(
            key,
            key_id=key_id,
            operation=f"{requester}.snapshot.response",
            timestamp=timestamp,
            body=service_response_bytes(request_bytes=request_bytes, response_body=body),
        ),
        "Cache-Control": "no-store",
    }


def request_headers(
    *, requester: str, owner: str, key_id: str, secret: bytes, framed: bytes
) -> dict[str, str]:
    """Build a signed request for any declared owner snapshot contract."""
    stamp = int(time.time())
    operation = f"{requester}.snapshot.read"
    key = ServiceKey(requester, owner, frozenset({operation}), secret)
    return {
        "X-Source-Key-Id": key_id,
        "X-Source-Issued-At": str(stamp),
        "X-Source-Signature": sign_service_body(
            key, key_id=key_id, operation=operation, timestamp=stamp, body=framed
        ),
    }


def verify_response(
    *,
    requester: str,
    owner: str,
    key_id: str,
    secret: bytes,
    framed: bytes,
    body: bytes,
    headers: Mapping[str, str],
) -> None:
    """Verify the response's bytes and the exact originating request before parsing."""
    operation = f"{requester}.snapshot.response"
    key = ServiceKey(owner, requester, frozenset({operation}), secret)
    verify_service_body(
        {key_id: key},
        key_id=headers.get("x-source-key-id", ""),
        issuer=owner,
        audience=requester,
        operation=operation,
        timestamp=headers.get("x-source-issued-at", ""),
        signature=headers.get("x-source-signature", ""),
        body=service_response_bytes(request_bytes=framed, response_body=body),
        now=int(time.time()),
    )
