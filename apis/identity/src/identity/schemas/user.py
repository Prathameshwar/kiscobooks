"""Request and response schemas for the user resource.

Credentials never appear here — no password, MFA secret, session or recovery code
(docs/identity-schema.md §4.1); those live in Authentik. ``authentik_sub``,
``status`` and ``user_type`` are not editable through the generic update: linking an
IdP, activating an invitation and deactivation are explicit lifecycle actions, not
field writes (api-conventions §CRUD).
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import Field, field_validator

from identity.models import IDENTITY_PROVIDERS
from identity.schemas.base import PageMeta, StrictModel, looks_like_email

#: Invite is for people who log in; platform_admin and service_account are provisioned
#: by other paths, so the invite form offers only these two.
_INVITABLE_USER_TYPES = frozenset({"tenant_user", "customer_portal_user"})


class UserInvite(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    salutation: str | None = Field(default=None, max_length=20)
    #: Derived from the name when omitted; stored, then user-editable.
    display_name: str | None = Field(default=None, max_length=200)
    user_type: str = "tenant_user"
    job_title: str | None = Field(default=None, max_length=120)
    employee_code: str | None = Field(default=None, max_length=40)
    phone_country_code: str | None = Field(default=None, max_length=8)
    phone: str | None = Field(default=None, max_length=20)
    default_company_id: uuid.UUID | None = None
    reporting_manager_id: uuid.UUID | None = None
    date_of_joining: dt.date | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return looks_like_email(v)

    @field_validator("user_type")
    @classmethod
    def _user_type(cls, v: str) -> str:
        if v not in _INVITABLE_USER_TYPES:
            raise ValueError(f"user_type must be one of {', '.join(sorted(_INVITABLE_USER_TYPES))}")
        return v


class UserUpdate(StrictModel):
    nonnullable = frozenset(["display_name", "first_name"])

    salutation: str | None = Field(default=None, max_length=20)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    job_title: str | None = Field(default=None, max_length=120)
    employee_code: str | None = Field(default=None, max_length=40)
    phone_country_code: str | None = Field(default=None, max_length=8)
    phone: str | None = Field(default=None, max_length=20)
    reporting_manager_id: uuid.UUID | None = None
    default_company_id: uuid.UUID | None = None
    default_department_id: uuid.UUID | None = None
    date_of_joining: dt.date | None = None
    date_of_exit: dt.date | None = None
    locale: str | None = Field(default=None, max_length=8)
    timezone: str | None = Field(default=None, max_length=64)
    date_format: str | None = Field(default=None, max_length=20)
    datetime_format: str | None = Field(default=None, max_length=30)
    digit_grouping: str | None = Field(default=None, max_length=10)
    currency_display: str | None = Field(default=None, max_length=20)
    theme: str | None = Field(default=None, max_length=20)
    landing_page: str | None = Field(default=None, max_length=100)


class UserListItem(StrictModel):
    id: uuid.UUID
    display_name: str
    email: str
    user_type: str
    status: str
    job_title: str | None
    updated_at: dt.datetime


class UserDetail(StrictModel):
    id: uuid.UUID
    user_type: str
    status: str
    salutation: str | None
    first_name: str
    middle_name: str | None
    last_name: str | None
    display_name: str
    email: str
    email_verified_at: dt.datetime | None
    phone_country_code: str | None
    phone: str | None
    phone_verified_at: dt.datetime | None
    employee_code: str | None
    job_title: str | None
    reporting_manager_id: uuid.UUID | None
    default_company_id: uuid.UUID | None
    default_department_id: uuid.UUID | None
    date_of_joining: dt.date | None
    date_of_exit: dt.date | None
    locale: str | None
    timezone: str | None
    date_format: str | None
    datetime_format: str | None
    digit_grouping: str | None
    currency_display: str | None
    theme: str | None
    landing_page: str | None
    invited_at: dt.datetime | None
    activated_at: dt.datetime | None
    deactivated_at: dt.datetime | None
    anonymized_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime


class UserPage(StrictModel):
    items: list[UserListItem]
    page: PageMeta


class CompanyUserInvite(StrictModel):
    """Only a new tenant person; company and account classification are fixed by the route."""

    email: str = Field(min_length=3, max_length=320)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return looks_like_email(value)


class DeactivateRequest(StrictModel):
    reason: str | None = Field(default=None, max_length=500)


class UserIdentityCreate(StrictModel):
    provider: str
    provider_sub: str = Field(min_length=1, max_length=255)

    @field_validator("provider")
    @classmethod
    def _provider(cls, v: str) -> str:
        if v not in IDENTITY_PROVIDERS:
            raise ValueError(f"provider must be one of {', '.join(sorted(IDENTITY_PROVIDERS))}")
        return v


class UserIdentityItem(StrictModel):
    id: uuid.UUID
    user_id: uuid.UUID
    provider: str
    provider_sub: str
    linked_at: dt.datetime
    last_login_at: dt.datetime | None
