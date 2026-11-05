"""Accounting's scoped Catalog lease for complete inventory master evidence."""

import datetime as dt
import hashlib
import uuid
from typing import Any, Literal

import httpx
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import SnapshotCredential, request_headers, verify_response
from billing_platform.service_auth import service_request_bytes
from pydantic import Field, field_validator

from reporting_contract.contract import Contract
from reporting_contract.transport import Owner


class CatalogStockOwner(SnapshotCredential):
    """Safe owner origin with explicit or live enrolled-company authorization."""

    owner: Literal["catalog"] = "catalog"
    origin: str
    key_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")

    @field_validator("origin")
    @classmethod
    def safe_origin(cls, value: str) -> str:
        return Owner.safe_origin(value)


class CatalogStockPage(Contract):
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    source_id: uuid.UUID
    as_of: dt.date
    expires_at: dt.datetime
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    record_count: int = Field(ge=0, le=10000)
    offset: int = Field(ge=0, le=10000)
    records: list[dict[str, Any]] = Field(max_length=200)
    next_offset: int | None


async def exchange(
    client: httpx.AsyncClient,
    owner: CatalogStockOwner,
    path: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    raw = canonical_json(body)
    framed = service_request_bytes(method="POST", path=path, query="", body=raw)
    headers = request_headers(
        requester="accounting",
        owner="catalog",
        key_id=owner.key_id,
        secret=owner.secret.get_secret_value().encode(),
        framed=framed,
    )
    headers["Content-Type"] = "application/json"
    async with client.stream(
        "POST", owner.origin + path, content=raw, headers=headers, follow_redirects=False
    ) as response:
        payload = bytearray()
        async for chunk in response.aiter_bytes():
            payload.extend(chunk)
            if len(payload) > 900000:
                raise ValueError("Catalog stock source page exceeds its byte bound")
        verify_response(
            requester="accounting",
            owner="catalog",
            key_id=owner.key_id,
            secret=owner.secret.get_secret_value().encode(),
            framed=framed,
            body=bytes(payload),
            headers=response.headers,
        )
        response.raise_for_status()
        import json

        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("Catalog stock source response is invalid")
        return value


async def acquire(
    client: httpx.AsyncClient,
    owner: CatalogStockOwner,
    *,
    tenant: uuid.UUID,
    company: uuid.UUID,
    identity: uuid.UUID,
    as_of: dt.date,
) -> tuple[CatalogStockPage, list[dict[str, Any]]]:
    body = {
        "tenant_id": str(tenant),
        "company_id": str(company),
        "source_id": str(identity),
        "as_of": as_of.isoformat(),
        "offset": 0,
        "release": False,
    }
    records: list[dict[str, Any]] = []
    first = None
    while True:
        page = CatalogStockPage.model_validate(
            await exchange(client, owner, "/internal/v1/stock-report-sources", body)
        )
        if (page.tenant_id, page.company_id, page.source_id, page.as_of, page.offset) != (
            tenant,
            company,
            identity,
            as_of,
            len(records),
        ):
            raise ConflictError("Catalog stock source page differs from the requested company cut")
        if first is None:
            first = page
        elif (page.policy_hash, page.content_hash, page.record_count, page.expires_at) != (
            first.policy_hash,
            first.content_hash,
            first.record_count,
            first.expires_at,
        ):
            raise ConflictError("Catalog stock source pages changed while copying")
        records.extend(page.records)
        if len(records) > page.record_count or (
            page.next_offset is not None and page.next_offset != len(records)
        ):
            raise ConflictError("Catalog stock source page leaves a gap or repeats records")
        if page.next_offset is None:
            break
        if not page.records:
            raise ConflictError("Catalog stock source page made no progress")
        body["offset"] = page.next_offset
    if (
        len(records) != first.record_count
        or hashlib.sha256(canonical_json(records, maximum_bytes=4 * 1024 * 1024)).hexdigest()
        != first.content_hash
    ):
        raise ConflictError("Catalog stock source manifest does not reconcile")
    return first, records
