from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import Field, field_validator, model_validator

from identity.schemas.base import StrictModel


def review_reason(value: str) -> str:
    value = value.strip()
    if len(value) < 3 or any(ord(character) < 32 for character in value):
        raise ValueError("enter a reason with 3 to 500 characters")
    return value


class AccountReviewItem(StrictModel):
    id: uuid.UUID
    name: str
    username: str
    email: str
    status: str
    created_at: dt.datetime
    needs_attention: bool


class AccountDecision(StrictModel):
    action: Literal["approve", "reject", "reopen"]
    version: int = Field(ge=1, strict=True)
    reason: str = Field(min_length=3, max_length=500)
    attested: bool = Field(default=False, strict=True)
    workspace_name: str | None = Field(default=None, max_length=200)

    _reason = field_validator("reason")(review_reason)

    @field_validator("workspace_name")
    @classmethod
    def clean_workspace(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("enter a valid workspace name")
        return value

    @model_validator(mode="after")
    def approval_attestation(self) -> AccountDecision:
        if self.action == "approve" and not self.attested:
            raise ValueError(
                "confirm that you independently checked the person's identity and email"
            )
        return self


class AccountCommand(StrictModel):
    id: uuid.UUID
    action: str
    reason: str
    attested: bool
    workspace_name: str | None
    status: str
    actor_id: uuid.UUID
    created_at: dt.datetime
    completed_at: dt.datetime | None
    error_code: str | None


class AccountReconciliation(StrictModel):
    version: int = Field(ge=1, strict=True)
    reason: str = Field(min_length=3, max_length=500)
    _reason = field_validator("reason")(review_reason)


class AccountHandoff(StrictModel):
    username: str
    sign_in_url: str
    invitation_url: str | None = None
    notification_status: Literal["queued", "manual"]


class AccountReviewDetail(AccountReviewItem):
    country_code: str
    state_code: str
    workspace_name: str | None
    provider_active: bool
    provider_verified: bool
    version: int
    updated_at: dt.datetime
    history: list[AccountCommand]
    handoff: AccountHandoff | None = None
