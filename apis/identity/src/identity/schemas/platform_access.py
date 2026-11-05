"""Closed platform administrator contract; no arbitrary user or role assignment."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from identity.schemas.base import StrictModel, looks_like_email
from identity.schemas.base import clean_text as clean_text


class PlatformAdministratorRole(StrictModel):
    id: uuid.UUID
    key: Literal["tenant_admin"] = "tenant_admin"
    name: str
    description: str | None
    is_system: Literal[True] = True
    scope_hint: Literal["tenant"] = "tenant"
    permissions: list[str]


class AdministratorTenant(StrictModel):
    id: uuid.UUID
    name: str
    status: str


class AdministratorListItem(StrictModel):
    id: uuid.UUID
    display_name: str
    email: str
    status: str
    updated_at: dt.datetime


class PlatformAdministrator(AdministratorListItem):
    tenant: AdministratorTenant
    assignment_id: uuid.UUID
    assignment_updated_at: dt.datetime
    assignment_active: bool
    valid_from: dt.date
    valid_to: dt.date | None
    last_active_administrator: bool
    recovery_deliveries: list[Literal["link", "email"]] = Field(default_factory=list)


class AdministratorInvite(StrictModel):
    display_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=320)
    reason: str = Field(min_length=3, max_length=500)
    _text = field_validator("display_name", "reason", mode="before")(clean_text)

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, value: str) -> str:
        value = clean_text(value)
        if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) is None:
            raise ValueError("enter a valid email address")
        return looks_like_email(value)


class AdministratorCommand(StrictModel):
    action: Literal["edit", "suspend", "restore", "revoke", "resend_invitation"]
    expected_updated_at: AwareDatetime
    expected_assignment_updated_at: AwareDatetime
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=500)
    _reason = field_validator("reason", mode="before")(clean_text)

    @model_validator(mode="after")
    def validate_edit(self) -> AdministratorCommand:
        if self.action == "edit":
            if self.display_name is None:
                raise ValueError("a display name is required")
            self.display_name = clean_text(self.display_name)
        elif self.display_name is not None:
            raise ValueError("display name is only accepted for an edit")
        return self


class AdministratorRecoveryRequest(StrictModel):
    delivery: Literal["link", "email"]
    expected_updated_at: AwareDatetime
    expected_assignment_updated_at: AwareDatetime
    reason: str = Field(min_length=3, max_length=500)
    _reason = field_validator("reason", mode="before")(clean_text)


class AdministratorRecoveryLink(StrictModel):
    delivery: Literal["link", "email"]
    tenant_id: uuid.UUID
    administrator_id: uuid.UUID
    recovery_url: str | None = None
    expires_at: dt.datetime


class AdministratorReceipt(StrictModel):
    tenant_id: uuid.UUID
    administrator_id: uuid.UUID
    assignment_id: uuid.UUID
    status: str
    assignment_active: bool
    updated_at: dt.datetime
    assignment_updated_at: dt.datetime
    invitation_id: uuid.UUID | None = None
    invitation_url: str | None = None
    invitation_expires_at: dt.datetime | None = None
