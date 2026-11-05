from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.snapshots import (
    SnapshotManifest,
    SnapshotPage,
    SnapshotRecord,
    manifest_digest,
)
from pydantic import SecretStr, ValidationError

from catalog.schemas.identity_source import CONTRACT, FACTS
from catalog.tasks.identity_source import (
    IdentitySourceSettings,
    IdentitySourceUnavailableError,
    fetch_identity_snapshot,
)
from tests.source_factories import company_record


def settings() -> IdentitySourceSettings:
    return IdentitySourceSettings(
        base_url="https://identity.example.test",
        request_secret=SecretStr("ephemeral-test-key" * 3),
        response_secrets={"current": SecretStr("ephemeral-response-key" * 3)},
    )


async def test_snapshot_client_stops_downloading_when_total_size_is_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_id, tenant, company = uuid7(), uuid7(), uuid7()
    records = [
        company_record(company),
        *(
            SnapshotRecord(
                kind="user", id=uuid7(), data={"status": "active", "padding": "x" * 300000}
            )
            for _ in range(100)
        ),
    ]
    pages = [
        SnapshotPage(snapshot_id=snapshot_id, page_number=i, records=(row,))
        for i, row in enumerate(records)
    ]
    digests = tuple(page.digest() for page in pages)
    now = utcnow()
    counts = {kind: 0 for kind in FACTS}
    counts.update(company=1, user=100)
    manifest = SnapshotManifest(
        contract=CONTRACT,
        snapshot_id=snapshot_id,
        tenant_id=tenant,
        company_id=company,
        source_version=2,
        generated_at=now,
        expires_at=now + dt.timedelta(seconds=60),
        record_count=101,
        page_sha256=digests,
        content_sha256=manifest_digest(digests),
        stream_counts=counts,
    )
    downloads = []

    async def request(*args: Any, **kwargs: Any) -> bytes:
        if kwargs["method"] == "POST":
            return manifest.model_dump_json().encode()
        number = int(kwargs["path"].rsplit("/", 1)[-1])
        downloads.append(number)
        return pages[number].wire_bytes()

    monkeypatch.setattr("catalog.tasks.identity_source._request", request)
    with pytest.raises(IdentitySourceUnavailableError):
        await fetch_identity_snapshot(
            settings(), tenant_id=tenant, company_id=company, request_id=uuid7()
        )
    assert len(downloads) < 40


@pytest.mark.parametrize(
    "url",
    [
        "http://external.test",
        "https://user:pass@identity.test",
        "https://identity.test/api",
        "https://identity.test?query=yes",
        "https://identity.test#fragment",
        "file:///tmp/data",
    ],
)
def test_source_transport_rejects_unsafe_base_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        IdentitySourceSettings.model_validate({**settings().model_dump(), "base_url": url})


def test_source_keys_and_scope_time_validation() -> None:
    from catalog.tasks.identity_source import validate_snapshot_scope
    from tests.source_factories import snapshot

    with pytest.raises(ValidationError):
        IdentitySourceSettings.model_validate(
            {**settings().model_dump(), "response_secrets": {"current": SecretStr("short")}}
        )
    tenant, company = uuid7(), uuid7()
    source = snapshot(tenant, company)
    for manifest in (
        source.manifest.model_copy(update={"tenant_id": uuid7()}),
        source.manifest.model_copy(update={"company_id": uuid7()}),
        source.manifest.model_copy(update={"expires_at": utcnow() - dt.timedelta(seconds=1)}),
        source.manifest.model_copy(update={"generated_at": utcnow() + dt.timedelta(minutes=1)}),
    ):
        with pytest.raises(IdentitySourceUnavailableError):
            validate_snapshot_scope(manifest, tenant_id=tenant, company_id=company)


async def test_snapshot_rejects_nil_request_scope() -> None:
    import uuid

    from billing_platform.errors import ValidationFailedError

    with pytest.raises(ValidationFailedError):
        await fetch_identity_snapshot(
            settings(), tenant_id=uuid.UUID(int=0), company_id=uuid7(), request_id=uuid7()
        )


async def test_single_response_download_is_bounded_before_signature_parsing() -> None:
    import httpx

    from catalog.tasks.identity_source import _request

    async def response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(b"x" * 1048577))

    async with httpx.AsyncClient(
        base_url=settings().base_url, transport=httpx.MockTransport(response)
    ) as client:
        with pytest.raises(IdentitySourceUnavailableError, match="bound"):
            await _request(client, settings(), method="GET", path="/bounded")
