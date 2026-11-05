from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field, field_validator

from identity.schemas.base import StrictModel, looks_like_email


class ContactCreate(StrictModel):
    type: Literal["primary", "finance", "support", "statutory"]
    name: str = Field(min_length=1, max_length=150)
    designation: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    phone_country_code: str | None = Field(default=None, pattern=r"^\+?[0-9]{1,7}$")
    phone: str | None = Field(default=None, pattern=r"^[0-9 ()+-]{3,20}$")
    is_primary: bool = Field(default=False, strict=True)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return looks_like_email(value) if value else value


class ContactItem(ContactCreate):
    id: uuid.UUID
    company_id: uuid.UUID
    is_active: bool


class ContactUpdate(ContactCreate):
    """Replacement of editable contact fields; lifecycle is a separate action."""


class PreferenceWrite(StrictModel):
    is_enabled: bool = Field(strict=True)


class PreferenceItem(PreferenceWrite):
    id: uuid.UUID
    user_id: uuid.UUID
    channel: str
    event_key: str
    source_version: int
