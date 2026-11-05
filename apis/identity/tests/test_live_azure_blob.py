"""Opt-in real Azurite HTTP checks; this does not prove cloud RBAC or delegation."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
from urllib.parse import urlencode

import httpx
import pytest
from azure.storage.blob import BlobSasPermissions, ContentSettings, generate_blob_sas
from azure.storage.blob.aio import BlobServiceClient
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7

from identity.config import AzureBlobSettings
from identity.models import CompanyDocument
from identity.services.documents import AzureDocumentStore


@pytest.mark.skipif(
    not os.environ.get("IDENTITY_TEST_AZURITE_URL"),
    reason="explicit local Azurite configuration required",
)
async def test_real_blob_create_only_checksum_snapshot_private_download():
    url = os.environ["IDENTITY_TEST_AZURITE_URL"]
    key = os.environ["IDENTITY_TEST_AZURITE_KEY"]
    assert url == "http://127.0.0.1:10000/billlocal"
    service = BlobServiceClient(url, credential=key, api_version="2025-11-05")
    container = "identity-test-" + uuid7().hex
    await service.create_container(container, public_access=None)
    store = AzureDocumentStore(
        AzureBlobSettings(
            account_url="https://unitstorage.blob.core.windows.net", container=container
        )
    )
    await store.service.close()
    store.service = service
    tenant, company, doc = uuid7(), uuid7(), uuid7()
    data = b"%PDF-1.7\nlocal integration evidence\n%%EOF"
    row = CompanyDocument(
        id=doc,
        tenant_id=tenant,
        company_id=company,
        file_url=f"identity/{tenant}/{company}/{doc}",
        file_size_bytes=len(data),
        content_type="application/pdf",
        content_sha256=hashlib.sha256(data).hexdigest(),
    )
    blob = service.get_blob_client(container, row.file_url)
    # Azurite does not implement cloud user-delegation keys; exercise service SAS on the wire.
    signature = generate_blob_sas(
        account_name="billlocal",
        container_name=container,
        blob_name=row.file_url,
        account_key=key,
        permission=BlobSasPermissions(create=True),
        expiry=utcnow() + dt.timedelta(minutes=5),
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            upload = await client.put(
                blob.url + "?" + signature,
                content=data,
                headers={"x-ms-blob-type": "BlockBlob", "Content-Type": "application/pdf"},
            )
            assert upload.status_code == 201, upload.status_code
            overwrite = await client.put(
                blob.url + "?" + signature,
                content=data,
                headers={"x-ms-blob-type": "BlockBlob", "Content-Type": "application/pdf"},
            )
            assert overwrite.status_code in {403, 409}
            assert (await client.get(blob.url)).status_code in {403, 404}
            row.blob_snapshot = await store.finalize(row)
            # A privileged later overwrite must never alter the finalized document.
            await blob.upload_blob(
                b"changed",
                overwrite=True,
                content_settings=ContentSettings(content_type="application/pdf"),
            )
            read_signature = generate_blob_sas(
                account_name="billlocal",
                container_name=container,
                blob_name=row.file_url,
                snapshot=row.blob_snapshot,
                account_key=key,
                permission=BlobSasPermissions(read=True),
                expiry=utcnow() + dt.timedelta(seconds=60),
            )
            result = await client.get(
                blob.url + "?" + read_signature + "&" + urlencode({"snapshot": row.blob_snapshot})
            )
            assert result.status_code == 200
            assert result.content == data
            # Cleanup is replayable and removes both base blob and orphan snapshots.
            await store.delete_pending(row)
            await store.delete_pending(row)
    finally:
        await service.delete_container(container)
        await store.close()
