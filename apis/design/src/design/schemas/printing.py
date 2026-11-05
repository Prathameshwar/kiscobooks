"""Scoped renderer transport; this contract cannot alter a design or voucher."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

#: One printed image, and every image on one layout together (designer plan §8 R2). Bytes
#: travel base64-encoded inside the signed resolution, whose body is bounded at 1 MiB by the
#: platform's service framing, so the images leave room for the layout itself.
PRINT_IMAGE_MAX_BYTES = 524_288
PRINT_IMAGES_MAX_BYTES = 655_360


class PrintPreview(BaseModel):
    """A saved version printed once for a person checking it, published or not (§8 R4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    template_id: uuid.UUID
    version_id: uuid.UUID


class PrintResolve(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    voucher_kind: Literal["PURCHASE"]
    voucher_type_id: uuid.UUID
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    preview: PrintPreview | None = None


class PrintAsset(BaseModel):
    """An image a layout names, with its bytes when it can print.

    ``status`` says why bytes are absent, so the renderer refuses with the reason instead of
    printing a page without the picture: ``WITHDRAWN`` (deactivated since it was placed),
    ``TOO_LARGE`` (over the one-image bound), ``OVER_BUDGET`` (the layout's images together
    are over their bound), ``MISSING`` (not this company's) or ``UNAVAILABLE`` (its stored
    bytes cannot be read or no longer match their digest: an operator's fault, not the author's).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    asset_id: uuid.UUID
    status: Literal["READY", "WITHDRAWN", "TOO_LARGE", "OVER_BUDGET", "MISSING", "UNAVAILABLE"]
    mime_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    content_base64: str | None = None


class PrintLayout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: Literal["BUILTIN", "CUSTOM"]
    name: str
    version: str
    template_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    assignment_rule_id: uuid.UUID | None = None
    layout_digest: str
    paper_size: str = "A4"
    page_orientation: str = "PORTRAIT"
    page_width_mm: str | None = None
    page_height_mm: str | None = None
    layout_definition: dict[str, Any] | None = None
    #: True only for a preview: the print says so on every page.
    preview: bool = False
    assets: list[PrintAsset] = Field(default_factory=list)
