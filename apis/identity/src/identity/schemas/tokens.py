from __future__ import annotations

import datetime as dt
import uuid

from pydantic import Field

from identity.schemas.base import StrictModel


class TokenCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    company_id: uuid.UUID | None = None
    permissions: list[str] = Field(min_length=1, max_length=100)
    expires_in_days: int = Field(default=30, ge=1, le=90, strict=True)


class TokenItem(StrictModel):
    id: uuid.UUID
    name: str
    token_prefix: str
    created_at: dt.datetime
    expires_at: dt.datetime | None
    revoked_at: dt.datetime | None
    last_used_at: dt.datetime | None


class TokenIssued(StrictModel):
    token: str
    details: TokenItem
