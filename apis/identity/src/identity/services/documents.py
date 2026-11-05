"""Azure private blobs: create-only upload SAS, verified content and immutable snapshots."""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
from typing import Protocol
from urllib.parse import urlencode

from azure.core import MatchConditions
from azure.core.exceptions import AzureError, ResourceModifiedError, ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob import BlobSasPermissions, generate_blob_sas
from azure.storage.blob.aio import BlobServiceClient
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PlatformError, ValidationFailedError
from fastapi import Request

from identity.config import AzureBlobSettings
from identity.models import CompanyDocument
from identity.schemas.documents import DocumentLink


class DocumentStorageUnavailableError(PlatformError):
    status_code = 503
    code = "document_storage_unavailable"


class DocumentStore(Protocol):
    async def link(self, row: CompanyDocument, *, upload: bool) -> DocumentLink: ...
    async def finalize(self, row: CompanyDocument) -> str: ...
    async def delete_pending(self, row: CompanyDocument) -> None: ...
    async def close(self) -> None: ...


def storage(request: Request) -> DocumentStore:
    value: DocumentStore | None = request.app.state.document_store
    if value is None:
        raise DocumentStorageUnavailableError("private document storage is not configured")
    return value


def object_key(row: CompanyDocument) -> str:
    # Never interpret historical URLs or any client-supplied key as a destination.
    expected = f"identity/{row.tenant_id}/{row.company_id}/{row.id}"
    if row.file_url != expected:
        raise ConflictError("document requires a reviewed storage migration")
    return expected


def validate_content(data: bytes, row: CompanyDocument) -> None:
    prefixes = {
        "application/pdf": b"%PDF-",
        "image/png": b"\x89PNG\r\n\x1a\n",
        "image/jpeg": b"\xff\xd8\xff",
    }
    if (
        len(data) != row.file_size_bytes
        or hashlib.sha256(data).hexdigest() != row.content_sha256
        or not data.startswith(prefixes.get(row.content_type or "", b"invalid"))
    ):
        raise ValidationFailedError("uploaded content does not match the declared file")


class AzureDocumentStore:
    def __init__(self, config: AzureBlobSettings) -> None:
        self.config = config
        self.credential = DefaultAzureCredential(
            managed_identity_client_id=config.managed_identity_client_id,
            exclude_interactive_browser_credential=True,
        )
        self.service = BlobServiceClient(
            config.account_url,
            credential=self.credential,
            retry_total=1,
            connection_timeout=5,
            read_timeout=10,
            logging_enable=False,
        )

    async def close(self) -> None:
        await self.service.close()
        await self.credential.close()

    async def _private(self) -> None:
        properties = await self.service.get_container_client(
            self.config.container
        ).get_container_properties()
        if properties.public_access:
            raise DocumentStorageUnavailableError("document container must be private")

    async def link(self, row: CompanyDocument, *, upload: bool) -> DocumentLink:
        key = object_key(row)
        now = utcnow()
        expiry = row.upload_expires_at if upload else now + dt.timedelta(seconds=60)
        if expiry is None or expiry <= now:
            raise ConflictError("upload has expired")
        if not upload and not row.blob_snapshot:
            raise ConflictError("document has not been finalized")
        try:
            async with asyncio.timeout(20):
                await self._private()
                start = now - dt.timedelta(minutes=5)
                delegation = await self.service.get_user_delegation_key(start, expiry)
                sas = generate_blob_sas(
                    account_name=self.service.account_name or "",
                    container_name=self.config.container,
                    blob_name=key,
                    user_delegation_key=delegation,
                    permission=BlobSasPermissions(create=True)
                    if upload
                    else BlobSasPermissions(read=True),
                    start=start,
                    expiry=expiry,
                    protocol="https",
                    snapshot=None if upload else row.blob_snapshot,
                    content_disposition=None if upload else 'attachment; filename="document"',
                    content_type=None if upload else "application/octet-stream",
                    cache_control="no-store",
                )
                url = self.service.get_blob_client(self.config.container, key).url + "?" + sas
                if not upload:
                    url += "&" + urlencode({"snapshot": row.blob_snapshot})
                return DocumentLink(
                    document_id=row.id,
                    url=url,
                    expires_at=expiry,
                    method="PUT" if upload else "GET",
                    headers={
                        "x-ms-blob-type": "BlockBlob",
                        "Content-Type": row.content_type or "",
                        "If-None-Match": "*",
                    }
                    if upload
                    else {},
                )
        except (AzureError, TimeoutError) as exc:
            raise DocumentStorageUnavailableError("document storage is unavailable") from exc

    async def finalize(self, row: CompanyDocument) -> str:
        blob = self.service.get_blob_client(self.config.container, object_key(row))
        try:
            async with asyncio.timeout(30):
                await self._private()
                properties = await blob.get_blob_properties()
                if (
                    properties.size != row.file_size_bytes
                    or properties.blob_type != "BlockBlob"
                    or properties.content_settings.content_type != row.content_type
                ):
                    raise ValidationFailedError("uploaded file properties do not match")
                download = await blob.download_blob(
                    etag=properties.etag,
                    match_condition=MatchConditions.IfNotModified,
                    max_concurrency=1,
                )
                data = bytearray()
                async for chunk in download.chunks():
                    data.extend(chunk)
                    if len(data) > (row.file_size_bytes or 0):
                        raise ValidationFailedError("uploaded file exceeds its declared size")
                validate_content(bytes(data), row)
                snapshot = await blob.create_snapshot(
                    etag=properties.etag, match_condition=MatchConditions.IfNotModified
                )
                return str(snapshot["snapshot"])
        except ResourceNotFoundError as exc:
            raise ConflictError("upload is not present") from exc
        except ResourceModifiedError as exc:
            raise ConflictError("upload changed during verification") from exc
        except (AzureError, TimeoutError) as exc:
            raise DocumentStorageUnavailableError("document storage is unavailable") from exc

    async def delete_pending(self, row: CompanyDocument) -> None:
        try:
            async with asyncio.timeout(20):
                await self._private()
                await self.service.get_blob_client(
                    self.config.container, object_key(row)
                ).delete_blob(delete_snapshots="include")
        except ResourceNotFoundError:
            return
        except (AzureError, TimeoutError) as exc:
            raise DocumentStorageUnavailableError("document storage is unavailable") from exc
