"""Request-bound Identity enrollment discovery; a capability is never a wildcard."""

import uuid
from typing import Literal

import httpx
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import (
    SnapshotCredential,
    request_headers,
    verify_response,
)
from billing_platform.service_auth import CompanyServiceScope, service_request_bytes
from pydantic import Field

from reporting_contract.authority import AuthoritySource
from reporting_contract.contract import Contract


class EnrollmentSource(AuthoritySource):
    requester: Literal["reports", "accounting", "catalog"] = "reports"


class EnrollmentQuery(Contract):
    purpose: Literal["collection", "retained"] = "collection"
    tenant_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    cursor: str | None = Field(default=None, max_length=4096)
    limit: int = Field(default=200, ge=1, le=200)


class EnrollmentPage(Contract):
    scopes: tuple[CompanyServiceScope, ...] = Field(max_length=200)
    next_cursor: str | None = None


async def scope_allowed(
    credential: SnapshotCredential,
    source: EnrollmentSource | None,
    tenant: uuid.UUID,
    company: uuid.UUID,
    *,
    retained: bool = False,
) -> bool:
    if any(
        s.tenant_id == tenant and s.company_id == company for s in credential.scopes
    ):
        return True
    if not credential.allow_enrolled_companies or source is None:
        return False
    async with httpx.AsyncClient(trust_env=False) as client:
        return await enrolled(client, source, tenant, company, retained=retained)


async def fetch_page(
    client: httpx.AsyncClient, source: EnrollmentSource, query: EnrollmentQuery
) -> EnrollmentPage:
    path = "/internal/v1/report-enrollments"
    raw = canonical_json(query.model_dump(mode="json"))
    framed = service_request_bytes(method="POST", path=path, query="", body=raw)
    secret = source.secret.get_secret_value().encode()
    headers = request_headers(
        requester=source.requester,
        owner="identity",
        key_id=source.key_id,
        secret=secret,
        framed=framed,
    )
    headers["Content-Type"] = "application/json"
    async with client.stream(
        "POST",
        source.origin + path,
        content=raw,
        headers=headers,
        follow_redirects=False,
        timeout=10,
    ) as response:
        response.raise_for_status()
        payload = bytearray()
        async for chunk in response.aiter_bytes():
            payload.extend(chunk)
            if len(payload) > 65536:
                raise ValueError("enrollment response exceeds its bound")
        verify_response(
            requester=source.requester,
            owner="identity",
            key_id=source.key_id,
            secret=secret,
            framed=framed,
            body=bytes(payload),
            headers=response.headers,
        )
    return EnrollmentPage.model_validate_json(payload)


async def enrolled(
    client: httpx.AsyncClient,
    source: EnrollmentSource,
    tenant: uuid.UUID,
    company: uuid.UUID,
    *,
    retained: bool = False,
) -> bool:
    page = await fetch_page(
        client,
        source,
        EnrollmentQuery(
            tenant_id=tenant,
            company_id=company,
            purpose="retained" if retained else "collection",
        ),
    )
    return any(s.tenant_id == tenant and s.company_id == company for s in page.scopes)


async def discover(
    client: httpx.AsyncClient, source: EnrollmentSource, *, retained: bool = False
) -> tuple[CompanyServiceScope, ...]:
    found: dict[tuple[uuid.UUID, uuid.UUID], CompanyServiceScope] = {}
    cursor = None
    seen: set[str] = set()
    for _ in range(1000):
        page = await fetch_page(
            client,
            source,
            EnrollmentQuery(
                cursor=cursor, purpose="retained" if retained else "collection"
            ),
        )
        for scope in page.scopes:
            found[(scope.tenant_id, scope.company_id)] = scope
        cursor = page.next_cursor
        if cursor is None:
            return tuple(found.values())
        if cursor in seen:
            raise ValueError("enrollment cursor did not advance")
        seen.add(cursor)
    raise ValueError("enrollment discovery exceeds its bound")
