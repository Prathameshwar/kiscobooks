"""Pydantic schemas for brand assets and reusable components.

The metadata a client may state is deliberately narrow (docs/invoice-design.md §6.3):

* ``storage_path`` and ``storage_backend`` are derived by the service. A client-supplied
  path can name another tenant's object.
* There is no ``public_url``: a public object URL contradicts CLAUDE.md §5.14, and a
  client-supplied URL ends up embedded in a rendered document.
* ``mime_type`` must match the asset type, and SVG is refused — it carries script and
  external references, which is the one thing a document renderer must not fetch.
* ``file_size_bytes``, ``content_digest`` and pixel dimensions are **never** taken from
  the request — they are measured from the uploaded bytes themselves (plan P4, 2026-11-03).

Images upload now; ``CUSTOM_FONT`` classifies an asset without a byte-storage path yet
(docs/invoice-design.md §9.2) — the one remaining open question this phase does not close.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AssetType = Literal[
    "LOGO",
    "SIGNATURE",
    "STAMP_SEAL",
    "WATERMARK",
    "HEADER_BANNER",
    "FOOTER_BANNER",
    "CUSTOM_FONT",
]

#: Raster images only. ``image/svg+xml`` is absent on purpose.
IMAGE_TYPES: frozenset[str] = frozenset({"image/png", "image/jpeg", "image/webp"})

#: A logo that does not fit in 5 MiB is a scanned document.
MAXIMUM_IMAGE_BYTES = 5 * 1024 * 1024

ComponentCategory = Literal[
    "HEADER", "BANK_DETAILS", "TERMS_CONDITIONS", "SIGNATORY", "TAX_SUMMARY", "FOOTER"
]

#: What a component block may hold: bounded labelled **text** a tenant composes — a bank
#: name, a terms paragraph, a signatory title. Keys are the tenant's own labels, so they
#: are not allowlisted; values are scalars, never markup or a stylesheet, and the renderer
#: prints them as text (escaped) exactly as it does an element's ``content``. Nothing here
#: becomes a structural attribute of the rendered document
#: (docs/invoice-design.md §6.2).
ComponentValue = Annotated[str, Field(max_length=2000)] | bool | int | float


class AssetUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_name: str = Field(min_length=1, max_length=128)
    asset_type: AssetType
    file_name: str = Field(
        min_length=1, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,253}$"
    )
    mime_type: str = Field(min_length=1, max_length=64)
    #: The bytes themselves, base64, written to this service's own private disk (plan
    #: P4/D3, 2026-11-03 — the same adapter Purchase PDFs use). Size, digest and (for PNG)
    #: pixel dimensions are measured from these bytes; a declared value is never trusted.
    content_base64: str = Field(min_length=4, max_length=7_000_000)
    #: Tenant-wide asset, usable by every company. Needs tenant-scoped authority.
    is_tenant_wide: bool = False

    @model_validator(mode="after")
    def media_type_matches_kind(self) -> AssetUpload:
        if self.asset_type == "CUSTOM_FONT":
            # Font bytes are not stored yet (docs/invoice-design.md §9.5); only image
            # assets can be uploaded in this phase.
            raise ValueError("font asset upload is not available yet")
        if self.mime_type not in IMAGE_TYPES:
            raise ValueError(f"an image asset must be one of {sorted(IMAGE_TYPES)}")
        return self


class AssetItem(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    asset_name: str
    asset_type: str
    file_name: str
    mime_type: str
    file_size_bytes: int
    image_width_px: int | None = None
    image_height_px: int | None = None
    is_active: bool
    created_at: dt.datetime
    #: A signed, expiring download (CLAUDE.md §5.14), minted fresh on every read — never
    #: stored. Absent when the reader asked for an inactive asset, which cannot be
    #: downloaded even by someone who may still see its metadata.
    download_token: str | None = None


class AssetDetail(AssetItem):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    tenant_id: uuid.UUID
    storage_backend: str
    storage_path: str
    content_digest: str | None = None
    created_by: uuid.UUID | None = None
    updated_at: dt.datetime


class ComponentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$")
    component_category: ComponentCategory
    description: str | None = Field(default=None, max_length=500)
    content_definition: dict[
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")], ComponentValue
    ] = Field(max_length=40)
    is_tenant_wide: bool = False


class ComponentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    content_definition: (
        dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")], ComponentValue] | None
    ) = Field(default=None, max_length=40)
    is_active: bool | None = None


class ComponentItem(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    code: str
    component_category: str
    description: str | None = None
    is_system: bool
    is_active: bool
    created_at: dt.datetime


class ComponentDetail(ComponentItem):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    tenant_id: uuid.UUID
    content_definition: dict[str, ComponentValue]
    created_by: uuid.UUID | None = None
    updated_at: dt.datetime
