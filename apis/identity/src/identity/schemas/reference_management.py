from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from billing_platform.reference.contracts import CatalogData
from pydantic import Field, computed_field, field_validator

from identity.domain.india_states import gst_state_codes
from identity.schemas.base import StrictModel

ReferenceKind = Literal["countries", "states", "languages", "currencies"]
KINDS = {
    "countries": "country",
    "states": "state",
    "languages": "language",
    "currencies": "currency",
}


class ReferenceItem(StrictModel):
    id: uuid.UUID
    code: str
    name: str
    parent_code: str | None
    is_active: bool
    version: int
    source: str

    @computed_field  # type: ignore[prop-decorator]  # Pydantic supports computed properties.
    @property
    def display_code(self) -> str:
        return (
            gst_state_codes().get(self.code, self.code) if self.parent_code == "IN" else self.code
        )


class ReferenceDetail(ReferenceItem):
    data: CatalogData
    sync_ready: bool
    updated_at: dt.datetime
    protected_fields: list[str]


class ReferenceUpdate(StrictModel):
    version: int = Field(strict=True, ge=0)
    data: CatalogData


class ReferenceLifecycle(StrictModel):
    version: int = Field(strict=True, ge=0)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def clean_reason(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if any(ord(character) < 32 or ord(character) == 127 for character in value):
                raise ValueError("control characters are not allowed")
        return value


class ReferenceOption(StrictModel):
    code: str
    name: str


class ReferenceOptions(StrictModel):
    countries: list[ReferenceOption]
    currencies: list[ReferenceOption]
