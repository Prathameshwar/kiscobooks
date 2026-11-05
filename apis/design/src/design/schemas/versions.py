"""Pydantic schemas for template versions.

A version carries the layout and nothing a client could use to bypass the designer:
there is no compiled HTML or CSS field, and ``version_number``, ``layout_digest`` and
``published_at`` are assigned by the service (docs/invoice-design.md §6.2).
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from design.schemas.canvas import CanvasDefinition


class VersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout_definition: CanvasDefinition
    change_summary: str | None = Field(default=None, max_length=255)


class VersionItem(BaseModel):
    """Lean list projection: the history, without every layout tree in it."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    template_id: uuid.UUID
    version_number: int
    schema_version: str
    layout_digest: str
    change_summary: str | None = None
    published_at: dt.datetime | None = None
    created_at: dt.datetime
    created_by: uuid.UUID | None = None


class VersionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    template_id: uuid.UUID
    version_number: int
    schema_version: str
    layout_definition: CanvasDefinition
    layout_digest: str
    change_summary: str | None = None
    published_at: dt.datetime | None = None
    published_by: uuid.UUID | None = None
    created_at: dt.datetime
    created_by: uuid.UUID | None = None
