"""Pydantic schemas for render snapshots — print evidence, never a mutation of one.

``storage_path`` is **derived**, like an asset's. It was briefly accepted from the body
on the theory that a trusted renderer reports where it wrote the artifact — but
``design.render.record`` is deliberately held by whoever issues documents, so the body is
user input, and a free-form key let a clerk record another tenant's object in the one
record meant to be trustworthy. The service computes the key and returns it; the renderer
writes there. ``rendered_by`` likewise comes from the signed actor context, never the body
(docs/invoice-design.md §6.3, §7).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OutputFormat = Literal["PDF", "HTML", "ZPL", "ESC_POS", "PNG"]
RenderChannel = Literal["PRINT", "PDF_DOWNLOAD", "EMAIL", "WHATSAPP", "CLIENT_PORTAL"]


class SnapshotRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voucher_id: uuid.UUID
    voucher_revision_id: uuid.UUID | None = None
    template_id: uuid.UUID
    template_version_id: uuid.UUID
    output_format: OutputFormat = "PDF"
    render_channel: RenderChannel
    checksum_sha256: str | None = Field(
        default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    file_size_bytes: int | None = Field(default=None, ge=1)
    render_duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)


class SnapshotItem(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    voucher_id: uuid.UUID
    voucher_revision_id: uuid.UUID | None = None
    template_id: uuid.UUID
    template_version_id: uuid.UUID
    output_format: str
    render_channel: str
    rendered_at: dt.datetime
    rendered_by: uuid.UUID | None = None


class SnapshotDetail(SnapshotItem):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    tenant_id: uuid.UUID
    company_id: uuid.UUID
    storage_path: str | None = None
    checksum_sha256: str | None = None
    file_size_bytes: int | None = None
    render_duration_ms: int | None = None
