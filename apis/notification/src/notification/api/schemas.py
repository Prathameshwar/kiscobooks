from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class PageMeta(StrictModel):
    next_cursor: str | None
    has_more: bool


class ProviderCapabilities(StrictModel):
    sns_topic_arn: str | None = Field(
        default=None,
        max_length=255,
        pattern=r"^arn:aws[a-z-]*:sns:[a-z0-9-]+:[0-9]{12}:[A-Za-z0-9_-]+$",
    )
    verification_token_ref: str | None = Field(default=None, min_length=1, max_length=500)


class ProviderCreate(StrictModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    callback_key: str = Field(min_length=32, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")
    channel: str
    provider_key: str = Field(min_length=1, max_length=60)
    display_name: str = Field(min_length=1, max_length=150)
    credential_ref: str = Field(min_length=1, max_length=500)
    callback_secret_ref: str | None = Field(default=None, max_length=500)
    region: str | None = Field(default=None, max_length=40)
    capabilities: ProviderCapabilities | None = None


class ProviderUpdate(StrictModel):
    expected_updated_at: AwareDatetime | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=150)
    credential_ref: str | None = Field(default=None, min_length=1, max_length=500)
    callback_secret_ref: str | None = Field(default=None, max_length=500)
    region: str | None = Field(default=None, max_length=40)
    capabilities: ProviderCapabilities | None = None
    status: Literal["pending", "active", "disabled"] | None = None

    @model_validator(mode="after")
    def required_values(self) -> ProviderUpdate:
        for name in {"display_name", "credential_ref", "status"} & self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ProviderItem(StrictModel):
    id: uuid.UUID
    key: str
    channel: str
    provider_key: str
    display_name: str
    region: str | None
    status: str
    updated_at: dt.datetime


class ProviderDetail(ProviderItem):
    callback_key: str
    credential_ref: str
    callback_secret_ref: str | None
    capabilities: dict[str, Any] | None
    created_at: dt.datetime


class ProviderPage(StrictModel):
    items: list[ProviderItem]
    page: PageMeta


class RequestItem(StrictModel):
    target_tenant_id: uuid.UUID | None
    id: uuid.UUID
    source_message_id: uuid.UUID
    company_id: uuid.UUID
    event_key: str
    category: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    status: str
    priority: int
    scheduled_at: dt.datetime | None
    received_at: dt.datetime


class RequestPage(StrictModel):
    items: list[RequestItem]
    page: PageMeta


class DeliveryItem(StrictModel):
    id: uuid.UUID
    request_id: uuid.UUID
    channel: str
    destination_masked: str
    status: str
    status_reason: str | None
    attempt_count: int
    next_attempt_at: dt.datetime | None
    created_at: dt.datetime


class DeliveryPage(StrictModel):
    items: list[DeliveryItem]
    page: PageMeta
