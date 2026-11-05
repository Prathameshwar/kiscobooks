"""Bounded authenticated snapshot acquisition outside Catalog DB transactions."""

from __future__ import annotations

import asyncio
import datetime as dt
import time
import uuid
from dataclasses import dataclass
from typing import Self
from urllib.parse import urlsplit

import httpx
from billing_platform.db.types import utcnow
from billing_platform.errors import PlatformError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.service_auth import (
    CompanyServiceScope,
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from billing_platform.snapshots import (
    MAX_SNAPSHOT_BYTES,
    SnapshotManifest,
    SnapshotPage,
    SnapshotRecord,
    verify_pages,
)
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from catalog.schemas.identity_source import validate_facts


class EnrollmentPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scopes: tuple[CompanyServiceScope, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, min_length=1, max_length=4096)


class IdentitySourceUnavailableError(PlatformError):
    status_code = 503
    code = "source_unavailable"


class IdentitySourceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    base_url: str
    request_key_id: str = Field(default="current", pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    request_secret: SecretStr = Field(min_length=32, repr=False)
    response_secrets: dict[str, SecretStr] = Field(min_length=1, max_length=4, repr=False)
    total_timeout_seconds: int = Field(default=30, strict=True, ge=1, le=60)

    @model_validator(mode="after")
    def secure_configuration(self) -> Self:
        url = urlsplit(self.base_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
            or (url.scheme == "http" and url.hostname not in {"127.0.0.1", "::1", "localhost"})
        ):
            raise ValueError(
                "Identity source requires HTTPS or explicit local development loopback"
            )
        if any(
            len(secret.get_secret_value().encode()) < 32
            for secret in self.response_secrets.values()
        ):
            raise ValueError("source response keys require at least 32 bytes")
        return self


@dataclass(frozen=True)
class VerifiedSnapshot:
    manifest: SnapshotManifest
    records: tuple[SnapshotRecord, ...]


def validate_snapshot_scope(
    manifest: SnapshotManifest, *, tenant_id: uuid.UUID, company_id: uuid.UUID
) -> None:
    now = utcnow()
    if (
        manifest.tenant_id != tenant_id
        or manifest.company_id != company_id
        or manifest.expires_at <= now
        or manifest.generated_at > now + dt.timedelta(seconds=5)
    ):
        raise IdentitySourceUnavailableError("Identity snapshot is stale or has an invalid scope")


async def _request(
    client: httpx.AsyncClient,
    settings: IdentitySourceSettings,
    *,
    method: str,
    path: str,
    body: bytes = b"",
    request_operation: str | None = None,
    response_operation: str = "catalog.snapshot.response",
    max_response_bytes: int = 1024 * 1024,
) -> bytes:
    framed = service_request_bytes(method=method, path=path, query="", body=body)
    stamp = int(time.time())
    operation = request_operation or (
        "catalog.snapshot.create" if method == "POST" else "catalog.snapshot.read"
    )
    key = ServiceKey(
        "catalog",
        "identity",
        frozenset({operation}),
        settings.request_secret.get_secret_value().encode(),
    )
    headers = {
        "content-type": "application/json",
        "accept-encoding": "identity",
        "x-source-key-id": settings.request_key_id,
        "x-source-issued-at": str(stamp),
        "x-source-signature": sign_service_body(
            key, key_id=settings.request_key_id, operation=operation, timestamp=stamp, body=framed
        ),
    }
    async with client.stream(method, path, content=body, headers=headers) as response:
        if (
            response.status_code != 200
            or response.headers.get("content-encoding", "identity") != "identity"
        ):
            raise IdentitySourceUnavailableError("Identity source request did not succeed")
        parts = []
        size = 0
        async for part in response.aiter_raw():
            size += len(part)
            if size > max_response_bytes:
                raise IdentitySourceUnavailableError("Identity source response exceeds its bound")
            parts.append(part)
        raw = b"".join(parts)
        verify_service_body(
            {
                key_id: ServiceKey(
                    "identity",
                    "catalog",
                    frozenset({response_operation}),
                    secret.get_secret_value().encode(),
                )
                for key_id, secret in settings.response_secrets.items()
            },
            key_id=response.headers.get("x-source-key-id", ""),
            issuer="identity",
            audience="catalog",
            operation=response_operation,
            timestamp=response.headers.get("x-source-issued-at", ""),
            signature=response.headers.get("x-source-signature", ""),
            now=int(time.time()),
            body=service_response_bytes(request_bytes=framed, response_body=raw),
        )
        return raw


async def fetch_identity_snapshot(
    settings: IdentitySourceSettings,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    request_id: uuid.UUID,
) -> VerifiedSnapshot:
    if any(value.int == 0 for value in (tenant_id, company_id, request_id)):
        raise ValidationFailedError("source request requires real scope and request identities")
    path = f"/internal/v1/tenants/{tenant_id}/companies/{company_id}/catalog-snapshots"
    try:
        async with (
            asyncio.timeout(settings.total_timeout_seconds),
            httpx.AsyncClient(
                base_url=settings.base_url, timeout=5, follow_redirects=False, trust_env=False
            ) as client,
        ):
            manifest = SnapshotManifest.model_validate_json(
                await _request(
                    client,
                    settings,
                    method="POST",
                    path=path,
                    body=canonical_json({"request_id": str(request_id)}),
                )
            )
            validate_snapshot_scope(manifest, tenant_id=tenant_id, company_id=company_id)
            pages = []
            downloaded = 0
            for number in range(len(manifest.page_sha256)):
                raw = await _request(
                    client,
                    settings,
                    method="GET",
                    path=f"{path}/{manifest.snapshot_id}/pages/{number}",
                )
                downloaded += len(raw)
                if downloaded > MAX_SNAPSHOT_BYTES + len(manifest.page_sha256) * 256:
                    raise IdentitySourceUnavailableError(
                        "Identity snapshot exceeds total download bound"
                    )
                pages.append(SnapshotPage.model_validate_json(raw))
            records = verify_pages(manifest, pages)
            validate_facts(manifest, records)
            validate_snapshot_scope(manifest, tenant_id=tenant_id, company_id=company_id)
            return VerifiedSnapshot(manifest, records)
    except (httpx.HTTPError, TimeoutError, ValueError, PlatformError) as exc:
        raise IdentitySourceUnavailableError("Identity source could not be verified") from exc


async def fetch_enrollments(settings: IdentitySourceSettings) -> tuple[CompanyServiceScope, ...]:
    """Fetch the complete signed list, or reject it without renewing any lease.

    At most 10,000 scopes / 100 pages and the configured total timeout. A bound
    failure never turns a partial list into authority or silently drops companies.
    """
    scopes: list[CompanyServiceScope] = []
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    cursors: set[str] = set()
    cursor: str | None = None
    try:
        async with (
            asyncio.timeout(settings.total_timeout_seconds),
            httpx.AsyncClient(
                base_url=settings.base_url, timeout=5, follow_redirects=False, trust_env=False
            ) as client,
        ):
            for _ in range(100):
                page = EnrollmentPage.model_validate_json(
                    await _request(
                        client,
                        settings,
                        method="POST",
                        path="/internal/v1/catalog-enrollments",
                        body=canonical_json({"limit": 200, "cursor": cursor}),
                        request_operation="catalog.enrollment.read",
                        response_operation="catalog.enrollment.response",
                        max_response_bytes=65536,
                    )
                )
                for scope in page.scopes:
                    identity = (scope.tenant_id, scope.company_id)
                    if identity in seen or len(scopes) >= 10000:
                        raise ValueError("duplicate or excessive enrollment scopes")
                    seen.add(identity)
                    scopes.append(scope)
                if page.next_cursor is None:
                    return tuple(scopes)
                if not page.scopes or page.next_cursor in cursors:
                    raise ValueError("enrollment cursor did not advance")
                cursors.add(page.next_cursor)
                cursor = page.next_cursor
            raise ValueError("enrollment discovery exceeded page bound")
    except (httpx.HTTPError, TimeoutError, ValueError, PlatformError) as exc:
        raise IdentitySourceUnavailableError(
            "Identity enrollment list could not be verified"
        ) from exc
