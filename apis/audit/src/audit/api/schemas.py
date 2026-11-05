"""Response contracts for the audit read surfaces.

Lean list items carry no ``changes``/``context`` JSON (api-conventions §list: a list never
returns unused JSON/TEXT columns); the detail view adds them plus the hash-chain values,
hex-encoded so an external auditor can re-verify a row. All PII-free — actors are ids,
resolved to names elsewhere (docs/audit.md §5.2).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class PageMeta(StrictModel):
    next_cursor: str | None
    has_more: bool


class AuditEventItem(StrictModel):
    """The lean audit-trail row."""

    id: uuid.UUID
    occurred_at: dt.datetime
    sequence: int
    category: str
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    actor_type: str | None
    actor_user_id: uuid.UUID | None
    on_behalf_of_user_id: uuid.UUID | None
    company_id: uuid.UUID | None
    department_id: uuid.UUID | None
    source_service: str | None
    trace_id: str | None


class AuditEventPage(StrictModel):
    items: list[AuditEventItem]
    page: PageMeta


class AuditEventDetail(StrictModel):
    """One event in full, including the before/after values and the chain proof."""

    id: uuid.UUID
    occurred_at: dt.datetime
    sequence: int
    category: str
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    actor_type: str | None
    actor_user_id: uuid.UUID | None
    on_behalf_of_user_id: uuid.UUID | None
    actor_ip: str | None
    actor_user_agent: str | None
    api_client_id: uuid.UUID | None
    company_id: uuid.UUID | None
    department_id: uuid.UUID | None
    changes: dict[str, Any] | None
    context: dict[str, Any] | None
    reason: str | None
    source_service: str | None
    trace_id: str | None
    request_id: str | None
    message_id: uuid.UUID
    #: Hex of the ``BINARY(32)`` chain values (§4.2). ``prev_hash`` is null on the first
    #: event of a tenant's chain.
    prev_hash: str | None
    row_hash: str


class ActivityItem(StrictModel):
    """The friendlier feed projection — "who did what to which entity" (§1)."""

    id: uuid.UUID
    occurred_at: dt.datetime
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    actor_type: str | None
    on_behalf_of_user_id: uuid.UUID | None
    source_service: str | None
    category: str
    company_id: uuid.UUID | None


class ActivityPage(StrictModel):
    items: list[ActivityItem]
    page: PageMeta


class ExportResult(StrictModel):
    """The result of an export — itself recorded as an ``access`` audit event (§5.3).

    The rows are returned inline for v1 (bounded by ``limit``); wiring the signed,
    expiring download URL to object storage is the deployment hook (CLAUDE.md §5.14).
    """

    export_id: uuid.UUID
    count: int
    truncated: bool
    events: list[AuditEventDetail]


class IntegrationLogCreate(StrictModel):
    integration_name: str = Field(min_length=1, max_length=100)
    direction: str = Field(min_length=1, max_length=20)  # inbound | outbound
    status: str = Field(min_length=1, max_length=20)  # success | failed | retrying
    response_code: int | None = Field(default=None, ge=100, le=599)
    retry_count: int = Field(default=0, ge=0)
    error_message: str | None = Field(default=None, max_length=500)
    metadata_json: dict[str, Any] | None = None


class IntegrationLogItem(StrictModel):
    id: uuid.UUID
    occurred_at: dt.datetime
    company_id: uuid.UUID | None
    integration_name: str
    direction: str
    status: str
    response_code: int | None
    retry_count: int
    error_message: str | None
    metadata_json: dict[str, Any] | None


class IntegrationLogPage(StrictModel):
    items: list[IntegrationLogItem]
    page: PageMeta

