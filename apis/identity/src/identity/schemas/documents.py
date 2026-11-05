"""Private document metadata. Storage keys and credentials never appear in list items."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import Field, model_validator

from identity.schemas.base import StrictModel

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


class DocumentWrite(StrictModel):
    type: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(min_length=1, max_length=200)
    # National identity numbers are never accepted as document metadata.
    file_size_bytes: int = Field(gt=0, le=MAX_DOCUMENT_BYTES, strict=True)
    content_type: Literal["application/pdf", "image/png", "image/jpeg"]
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_on: dt.date | None = None
    expires_on: dt.date | None = None

    @model_validator(mode="after")
    def dates(self) -> Self:
        if self.issued_on and self.expires_on and self.expires_on < self.issued_on:
            raise ValueError("expiry precedes issue date")
        if not self.title.strip():
            raise ValueError("title is blank")
        return self


class DocumentItem(StrictModel):
    id: uuid.UUID
    company_id: uuid.UUID
    type: str
    title: str
    file_size_bytes: int | None
    content_type: str | None
    storage_state: str
    issued_on: dt.date | None
    expires_on: dt.date | None
    is_active: bool
    finalized_at: dt.datetime | None


class DocumentLink(StrictModel):
    document_id: uuid.UUID
    url: str
    expires_at: dt.datetime
    method: Literal["PUT", "GET"]
    headers: dict[str, str] = Field(default_factory=dict)


class ReconcileResult(StrictModel):
    expired: int
