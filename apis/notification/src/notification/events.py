"""The inbound send-command contract carried over RabbitMQ.

Business services do not call a send API (docs/notification.md §2.1, §7); they write a
send command to their transactional outbox, which is delivered here as a
``MessageEnvelope`` (``billing_platform.messages``) whose ``payload`` is a
``SendCommand``. The envelope supplies ``message_id`` (the idempotency key stored as
``notification_request.source_message_id``), ``tenant_id``, ``occurred_at`` and
``trace_id``; this payload supplies everything the planning transaction needs.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from notification.domain.constants import CATEGORIES, CHANNELS


class SendCommand(BaseModel):
    """The versioned payload of a notification send command. ``extra='forbid'`` — an
    unknown field is a producer/consumer contract drift, not silently ignored."""

    model_config = ConfigDict(extra="forbid")

    company_id: uuid.UUID
    source_service: str = Field(min_length=1, max_length=40)
    source_event_key: str = Field(min_length=1, max_length=120)
    event_key: str = Field(min_length=1, max_length=120)
    category: str
    aggregate_type: str = Field(min_length=1, max_length=80)
    aggregate_id: uuid.UUID
    subject_type: str = Field(min_length=1, max_length=40)
    subject_id: uuid.UUID
    #: Channels to attempt, in order. Each is resolved and gated independently.
    channels: list[str] = Field(min_length=1, max_length=4)
    locale: str | None = Field(default=None, max_length=35)
    #: Template variables. Encrypted at rest as the request context snapshot.
    variables: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=0, le=9)
    source_version: int | None = Field(default=None, ge=1)
    correlation_id: uuid.UUID | None = None
    causation_id: uuid.UUID | None = None
    scheduled_at: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def timing_and_channels(self) -> SendCommand:
        if len(set(self.channels)) != len(self.channels):
            raise ValueError("duplicate notification channels")
        if self.scheduled_at and self.expires_at and self.scheduled_at >= self.expires_at:
            raise ValueError("notification must be scheduled before expiry")
        return self

    def validate_vocabulary(self) -> None:
        """Category and channels must be known — a code catalogue, checked before any
        row is written (raises ``ValueError`` the caller maps to a reject)."""
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown category: {self.category!r}")
        unknown = sorted(set(self.channels) - CHANNELS)
        if unknown:
            raise ValueError(f"unknown channels: {unknown}")


class PreferenceChanged(BaseModel):
    """Payload of ``identity``'s ``user_notification_preference.changed`` event.

    ``identity`` is master; this service projects the row read-only. ``source_version``
    is the monotonic version from the master — the projection applies an event only when
    it is newer, so out-of-order or replayed events are idempotent (docs/notification.md,
    docs/identity-schema.md §4.3).
    """

    model_config = ConfigDict(extra="forbid")

    subject_type: str = Field(min_length=1, max_length=40)
    subject_id: uuid.UUID
    event_key: str = Field(min_length=1, max_length=120)
    channel: str
    is_enabled: bool
    source_version: int = Field(ge=1)
    source_updated_at: dt.datetime
