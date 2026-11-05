"""Schemas for tenant self-service (the actor's own tenant).

Platform-managed fields — ``status``, ``plan_id``, ``suspended_*``, ``slug`` (immutable)
— are not accepted here: suspension and provisioning are platform-ops, and a slug rename
would silently break saved URLs and webhook targets.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import Field, field_validator

from identity.schemas.base import StrictModel, clean_text, looks_like_email


class TenantUpdate(StrictModel):
    nonnullable = frozenset(
        [
            "default_country_code",
            "default_currency_code",
            "default_locale",
            "default_timezone",
            "name",
            "primary_contact_email",
        ]
    )

    name: str | None = Field(default=None, min_length=1, max_length=200)
    primary_contact_email: str | None = Field(default=None, min_length=3, max_length=320)
    default_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    default_state_code: str | None = Field(default=None, min_length=1, max_length=6)
    default_currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    default_locale: str | None = Field(default=None, pattern=r"^[a-z]{2}$")
    default_timezone: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return clean_text(value)

    @field_validator("primary_contact_email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        return None if v is None else looks_like_email(v)


class TenantDetail(StrictModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    plan_id: uuid.UUID | None
    primary_contact_email: str
    default_country_code: str
    default_state_code: str | None
    default_currency_code: str
    default_locale: str
    default_timezone: str
    trial_ends_on: dt.date | None
    created_at: dt.datetime
    updated_at: dt.datetime
