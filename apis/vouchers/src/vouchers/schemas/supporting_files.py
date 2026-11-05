"""Bounded supporting-file transport; bytes are never part of voucher capture."""

import uuid
from typing import Literal

from pydantic import Field, field_validator

from vouchers.schemas.configuration import Contract, Version


class SupportingFileUpload(Version):
    filename: str = Field(min_length=1, max_length=160)
    media_type: Literal["application/pdf", "image/png", "image/jpeg", "text/plain"]
    content_base64: str = Field(min_length=4, max_length=13981016)

    @field_validator("filename")
    @classmethod
    def safe_name(cls, value: str) -> str:
        if any(ord(char) < 32 or char in "/\\" for char in value) or not value.strip():
            raise ValueError("invalid filename")
        return value.strip()


class SupportingFileDetail(Contract):
    id: uuid.UUID
    company_id: uuid.UUID
    voucher_id: uuid.UUID
    object_key: str
    content_hash: str
    media_type: Literal["application/pdf", "image/png", "image/jpeg", "text/plain"]
    size_bytes: int
    filename: str
    download_token: str | None = None


class SupportingFileRegistration(Version):
    """Hash-bound command identity, so receipt storage never carries file bytes."""

    filename: str
    media_type: str
    content_hash: str
    size_bytes: int
