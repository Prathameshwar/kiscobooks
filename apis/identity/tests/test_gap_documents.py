from __future__ import annotations

import datetime as dt
import hashlib
import uuid

import httpx
import pytest
from billing_platform.db.platform_models import Outbox
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import CompanyDocument
from identity.schemas.documents import DocumentLink
from identity.services.documents import (
    DocumentStorageUnavailableError,
    object_key,
    validate_content,
)
from tests.api_support import actor_headers, grant
from tests.factories import seed_two_companies

DATA = b"%PDF-1.7\nsynthetic test document\n%%EOF"
BODY = {
    "type": "incorporation",
    "title": "Private certificate",
    "file_size_bytes": len(DATA),
    "content_type": "application/pdf",
    "content_sha256": hashlib.sha256(DATA).hexdigest(),
}


class MemoryStore:
    def __init__(self) -> None:
        self.content: dict[str, bytes] = {}
        self.failed = False
        self.finalizations = 0

    async def link(self, row: CompanyDocument, *, upload: bool) -> DocumentLink:
        if self.failed:
            raise DocumentStorageUnavailableError("unavailable")
        key = object_key(row)
        expiry = row.upload_expires_at if upload else utcnow() + dt.timedelta(seconds=60)
        assert expiry
        if expiry <= utcnow():
            raise ConflictError("expired")
        return DocumentLink(
            document_id=row.id,
            url="https://storage.test/" + key,
            expires_at=expiry,
            method="PUT" if upload else "GET",
        )

    async def finalize(self, row: CompanyDocument) -> str:
        self.finalizations += 1
        data = self.content.get(object_key(row))
        if data is None:
            raise ConflictError("not uploaded")
        validate_content(data, row)
        return "immutable-snapshot"

    async def delete_pending(self, row: CompanyDocument) -> None:
        if self.failed:
            raise DocumentStorageUnavailableError("unavailable")
        self.content.pop(object_key(row), None)

    async def close(self) -> None:
        pass


async def test_document_lifecycle_replay_scope_and_redaction(
    app: FastAPI,
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, other = await seed_two_companies(session, tenant_a, tenant_b)
    provider = MemoryStore()
    app.state.document_store = provider
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["company.read", "company.update"], scope_type="company", scope_id=company)],
    )
    document_id = uuid7()
    root = f"/v1/companies/{company}/documents"
    url = root + f"/{document_id}"
    for _ in range(2):
        result = await client.put(url + "/upload", json=BODY, headers=headers)
        assert result.status_code == 200, result.text
        assert result.headers["cache-control"] == "no-store"
    assert (
        await client.put(url + "/upload", json={**BODY, "title": "changed"}, headers=headers)
    ).status_code == 409
    assert (await client.post(url + "/download", headers=headers)).status_code == 409
    assert (await client.post(url + "/finalize", headers=headers)).status_code == 409
    key = f"identity/{tenant_a}/{company}/{document_id}"
    provider.content[key] = b"invalid"
    assert (await client.post(url + "/finalize", headers=headers)).status_code == 422
    provider.content[key] = DATA
    for _ in range(2):
        result = await client.post(url + "/finalize", headers=headers)
        assert result.status_code == 200, result.text
        assert result.json()["storage_state"] == "ready"
    assert provider.finalizations == 3
    downloaded = await client.post(url + "/download", headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.headers["cache-control"] == "no-store"
    listed = await client.get(root, headers=headers)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 1
    for secret in ("file_url", "blob_snapshot", "content_sha256", "identity/"):
        assert secret not in listed.text
    for active in (False, False, True):
        response = await client.post(
            url + "/lifecycle", json={"is_active": active, "reason": "reviewed"}, headers=headers
        )
        assert response.status_code == 200, response.text
        if not active:
            assert (await client.post(url + "/download", headers=headers)).status_code == 409
    assert (await client.post(url + "/download")).status_code == 401
    denied = actor_headers(tenant_id=tenant_a, user_id=uuid7())
    assert (await client.get(root, headers=denied)).status_code == 403
    for suffix in ("/finalize", "/download", "/lifecycle"):
        response = await client.post(
            url.replace(str(company), str(other)) + suffix,
            headers=headers,
            json={"is_active": False, "reason": "test"} if suffix == "/lifecycle" else None,
        )
        assert response.status_code == 403
    other_headers = actor_headers(
        tenant_id=tenant_b, user_id=uuid7(), grants=[grant(["company.read", "company.update"])]
    )
    assert (
        await client.post(
            f"/v1/companies/{other}/documents/{document_id}/download", headers=other_headers
        )
    ).status_code == 404
    with tenant_scope(tenant_b):
        assert await session.get(CompanyDocument, document_id) is None
    with tenant_scope(tenant_a):
        events = list(
            await session.scalars(
                select(Outbox).where(Outbox.event_type.like("company.document_%"))
            )
        )
        assert len(events) == 5
        assert BODY["title"] not in str([event.payload for event in events])
        assert BODY["content_sha256"] not in str([event.payload for event in events])


async def test_upload_expiry_cleanup_and_failure_rollback(
    app: FastAPI,
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.read", "company.update"])]
    )
    root = f"/v1/companies/{company}/documents"
    document_id = uuid7()
    url = root + f"/{document_id}"
    assert (await client.put(url + "/upload", json=BODY, headers=headers)).status_code == 503
    provider = MemoryStore()
    app.state.document_store = provider
    provider.failed = True
    assert (await client.put(url + "/upload", json=BODY, headers=headers)).status_code == 503
    with tenant_scope(tenant_a):
        assert await session.get(CompanyDocument, document_id) is None
        assert not list(
            await session.scalars(
                select(Outbox).where(Outbox.event_type == "company.document_upload_requested")
            )
        )
    provider.failed = False
    assert (await client.put(url + "/upload", json=BODY, headers=headers)).status_code == 200
    with tenant_scope(tenant_a):
        row = await session.get(CompanyDocument, document_id)
        assert row
        row.upload_expires_at = utcnow() - dt.timedelta(minutes=2)
        await session.commit()
    assert (await client.post(url + "/finalize", headers=headers)).status_code == 409
    assert (await client.put(url + "/upload", json=BODY, headers=headers)).status_code == 409
    assert (
        await client.post(
            url + "/lifecycle", json={"is_active": False, "reason": "expired"}, headers=headers
        )
    ).status_code == 409
    provider.failed = True
    assert (await client.post(root + "/reconcile", headers=headers)).status_code == 503
    provider.failed = False
    for count in (1, 0):
        result = await client.post(root + "/reconcile", headers=headers)
        assert result.status_code == 200, result.text
        assert result.json() == {"expired": count}
    with tenant_scope(tenant_a):
        await session.refresh(row)
        assert row.storage_state == "expired"
        assert not row.is_active
    for patch in (
        {"file_size_bytes": 0},
        {"file_size_bytes": True},
        {"file_size_bytes": 30_000_000},
        {"content_type": "text/html"},
        {"content_sha256": "invalid"},
        {"title": " "},
        {"issued_on": "2026-02-02", "expires_on": "2026-01-01"},
        {"file_url": "https://evil.test"},
    ):
        assert (
            await client.put(root + f"/{uuid7()}/upload", json={**BODY, **patch}, headers=headers)
        ).status_code == 422


@pytest.mark.parametrize(
    "data,mime",
    [
        (b"%PDF-1.7", "application/pdf"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
    ],
)
def test_content_checksum_and_type(data: bytes, mime: str) -> None:
    row = CompanyDocument(
        file_size_bytes=len(data),
        content_sha256=hashlib.sha256(data).hexdigest(),
        content_type=mime,
    )
    validate_content(data, row)
    row.content_sha256 = "0" * 64
    with pytest.raises(ValidationFailedError):
        validate_content(data, row)
    row.content_sha256 = hashlib.sha256(data).hexdigest()
    row.content_type = "text/html"
    with pytest.raises(ValidationFailedError):
        validate_content(data, row)
