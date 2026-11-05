"""Closed print contracts: the browser supplies identities, never document content."""

import uuid
from typing import Literal

from billing_platform.service_auth import CompanyServiceScope
from pydantic import Field, SecretStr, field_validator

from vouchers.schemas.configuration import Contract, Version


class LayoutPreview(Contract):
    """One saved design version to print this bill on once, to check it (designer plan R4)."""

    template_id: uuid.UUID
    version_id: uuid.UUID


class PrintCreate(Version):
    revision_id: uuid.UUID
    #: Absent for an ordinary print. Present, the PDF uses that version, published or not,
    #: and says on every page that it is a layout preview.
    layout_preview: LayoutPreview | None = None


class PrintJobDetail(Contract):
    id: uuid.UUID
    company_id: uuid.UUID
    voucher_id: uuid.UUID
    revision_id: uuid.UUID
    status: Literal["PENDING", "RUNNING", "READY", "FAILED"]
    attempt: int
    layout_name: str
    layout_version: str
    document_status: str
    revision_number: int
    content_hash: str | None = None
    size_bytes: int | None = None
    failure_code: str | None = None
    download_token: str | None = None


class PrintLayoutOwner(Contract):
    origin: str
    secret: SecretStr = Field(min_length=32, repr=False)
    scopes: list[CompanyServiceScope] = Field(min_length=1, max_length=1000)

    @field_validator("origin")
    @classmethod
    def secure_origin(cls, value: str) -> str:
        from vouchers.schemas.owners import Owner

        return Owner.https_origin(value)
