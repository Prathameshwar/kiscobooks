"""Azure SDK adapter contract tests; live Azure authorization is a separate gate."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from azure.core import MatchConditions
from azure.core.exceptions import AzureError, ResourceModifiedError, ResourceNotFoundError
from azure.storage.blob import UserDelegationKey
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from pydantic import ValidationError

from identity.config import AzureBlobSettings
from identity.models import CompanyDocument
from identity.services.documents import (
    AzureDocumentStore,
    DocumentStorageUnavailableError,
    object_key,
)


@pytest.fixture
def blob_document():
    tenant, company, document = uuid7(), uuid7(), uuid7()
    data = b"%PDF-1.7\nsynthetic content"
    return CompanyDocument(
        id=document,
        tenant_id=tenant,
        company_id=company,
        file_url=f"identity/{tenant}/{company}/{document}",
        file_size_bytes=len(data),
        content_type="application/pdf",
        content_sha256=hashlib.sha256(data).hexdigest(),
        upload_expires_at=utcnow() + dt.timedelta(minutes=5),
    ), data


class Chunks:
    def __init__(self, data):
        self.data = data

    async def chunks(self):
        yield self.data[:5]
        yield self.data[5:]


@pytest.fixture
def adapter(blob_document):
    row, data = blob_document
    config = AzureBlobSettings(
        account_url="https://unitstorage.blob.core.windows.net", container="identity-private"
    )
    store = AzureDocumentStore(config)
    # Construction opens no connections; mocks replace the SDK boundary for this unit test.
    store.credential = SimpleNamespace(close=AsyncMock())
    blob = SimpleNamespace(
        url=config.account_url + "/identity-private/" + row.file_url,
        get_blob_properties=AsyncMock(
            return_value=SimpleNamespace(
                size=len(data),
                blob_type="BlockBlob",
                content_settings=SimpleNamespace(content_type=row.content_type),
                etag='"original"',
            )
        ),
        download_blob=AsyncMock(return_value=Chunks(data)),
        create_snapshot=AsyncMock(return_value={"snapshot": "2026-09-12T12:00:00.0000000Z"}),
        delete_blob=AsyncMock(),
    )
    delegation = UserDelegationKey()
    delegation.signed_oid = str(uuid7())
    delegation.signed_tid = str(uuid7())
    delegation.signed_start = "2026-09-12T00:00:00Z"
    delegation.signed_expiry = "2026-09-13T00:00:00Z"
    delegation.signed_service = "b"
    delegation.signed_version = "2025-11-05"
    delegation.value = base64.b64encode(secrets.token_bytes(32)).decode()
    container = SimpleNamespace(
        get_container_properties=AsyncMock(return_value=SimpleNamespace(public_access=None))
    )
    store.service = SimpleNamespace(
        account_name="unitstorage",
        get_container_client=Mock(return_value=container),
        get_blob_client=Mock(return_value=blob),
        get_user_delegation_key=AsyncMock(return_value=delegation),
        close=AsyncMock(),
    )
    return store, blob, container


async def test_signed_links_have_minimum_authority_and_snapshot(adapter, blob_document):
    store, blob, _ = adapter
    row, _ = blob_document
    upload = await store.link(row, upload=True)
    query = parse_qs(urlsplit(upload.url).query)
    assert query["sp"] == ["c"]
    assert query["spr"] == ["https"]
    assert upload.headers["If-None-Match"] == "*"
    with pytest.raises(ConflictError):
        await store.link(row, upload=False)
    row.blob_snapshot = await store.finalize(row)
    blob.download_blob.assert_awaited_once_with(
        etag='"original"', match_condition=MatchConditions.IfNotModified, max_concurrency=1
    )
    blob.create_snapshot.assert_awaited_once_with(
        etag='"original"', match_condition=MatchConditions.IfNotModified
    )
    download = await store.link(row, upload=False)
    query = parse_qs(urlsplit(download.url).query)
    assert query["sp"] == ["r"]
    assert query["snapshot"] == [row.blob_snapshot]
    assert query["sr"] == ["bs"]
    assert query["rscd"] == ['attachment; filename="document"']
    assert query["rsct"] == ["application/octet-stream"]
    assert 0 < (download.expires_at - utcnow()).total_seconds() <= 60
    await store.close()
    store.service.close.assert_awaited_once()
    store.credential.close.assert_awaited_once()


async def test_private_container_and_object_key_fail_closed(adapter, blob_document):
    store, _, container = adapter
    row, _ = blob_document
    container.get_container_properties.return_value.public_access = "blob"
    with pytest.raises(DocumentStorageUnavailableError):
        await store.link(row, upload=True)
    with pytest.raises(DocumentStorageUnavailableError):
        await store.finalize(row)
    with pytest.raises(DocumentStorageUnavailableError):
        await store.delete_pending(row)
    row.file_url = "https://external.test/path"
    with pytest.raises(ConflictError):
        object_key(row)


@pytest.mark.parametrize(
    "error,expected",
    [
        (ResourceNotFoundError(), ConflictError),
        (ResourceModifiedError(), ConflictError),
        (AzureError("provider unavailable"), DocumentStorageUnavailableError),
        (TimeoutError(), DocumentStorageUnavailableError),
    ],
)
async def test_finalize_provider_failures_are_redacted(adapter, blob_document, error, expected):
    store, blob, _ = adapter
    blob.get_blob_properties.side_effect = error
    with pytest.raises(expected):
        await store.finalize(blob_document[0])


async def test_properties_checksum_overflow_and_reconciliation(adapter, blob_document):
    store, blob, _ = adapter
    row, data = blob_document
    blob.get_blob_properties.return_value.size += 1
    with pytest.raises(ValidationFailedError):
        await store.finalize(row)
    blob.get_blob_properties.return_value.size = len(data)
    blob.download_blob.return_value = Chunks(data + b"excess")
    with pytest.raises(ValidationFailedError):
        await store.finalize(row)
    blob.download_blob.return_value = Chunks(b"x" * len(data))
    with pytest.raises(ValidationFailedError):
        await store.finalize(row)
    blob.create_snapshot.assert_not_awaited()
    await store.delete_pending(row)
    blob.delete_blob.assert_awaited_once_with(delete_snapshots="include")
    blob.delete_blob.side_effect = ResourceNotFoundError()
    await store.delete_pending(row)
    blob.delete_blob.side_effect = AzureError("provider unavailable")
    with pytest.raises(DocumentStorageUnavailableError):
        await store.delete_pending(row)
    row.upload_expires_at = utcnow() - dt.timedelta(seconds=1)
    with pytest.raises(ConflictError):
        await store.link(row, upload=True)
    row.upload_expires_at = utcnow() + dt.timedelta(minutes=1)
    store.service.get_user_delegation_key.side_effect = AzureError("provider unavailable")
    with pytest.raises(DocumentStorageUnavailableError):
        await store.link(row, upload=True)


@pytest.mark.parametrize(
    "config",
    [
        {"account_url": "http://unitstorage.blob.core.windows.net", "container": "private"},
        {"account_url": "https://external.test", "container": "private"},
        {
            "account_url": "https://unitstorage.blob.core.windows.net?sig=secret",
            "container": "private",
        },
        {"account_url": "https://unitstorage.blob.core.windows.net", "container": "bad--name"},
        {"account_url": "https://unitstorage.blob.core.windows.net", "container": "A"},
    ],
)
def test_storage_configuration_rejects_unsafe_endpoints(config):
    with pytest.raises(ValidationError):
        AzureBlobSettings(**config)
