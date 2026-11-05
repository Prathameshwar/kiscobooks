"""Versioned broker envelope shared by producers and consumers."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MessageEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: uuid.UUID
    tenant_id: uuid.UUID
    event_type: str = Field(min_length=3, max_length=120)
    schema_version: int = Field(ge=1, le=32767)
    occurred_at: dt.datetime
    trace_id: str | None = Field(default=None, max_length=32)
    payload: dict[str, Any]

    def model_post_init(self, __context: Any) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
